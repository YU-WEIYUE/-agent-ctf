"""Restricted argv executor using BoxPwnr's real execution result structure."""

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from ctf_forge._vendor.boxpwnr.executors.base_executor import RawExecutionResult
from ctf_forge.config import SandboxSettings
from ctf_forge.core.exceptions import ForgeError


def docker_command(settings: SandboxSettings) -> list[str]:
    if settings.wsl_distro and os.name == "nt":
        if not shutil.which("wsl"):
            raise ForgeError("WSL executable missing")
        return ["wsl", "-d", settings.wsl_distro, "-u", "root", "--exec", "docker"]
    executable = shutil.which("docker")
    if not executable:
        raise ForgeError("Docker CLI missing. No host execution fallback is allowed.")
    return [executable]


def mount_path(path: Path, settings: SandboxSettings) -> str:
    value = str(path)
    if settings.wsl_distro and os.name == "nt":
        value = path.as_posix()
        if len(value) < 3 or value[1:3] != ":/":
            raise ForgeError("Only local Windows drive paths are supported for WSL mounts")
        return f"/mnt/{value[0].lower()}/{value[3:]}"
    return value


def bounded_run(argv: list[str], timeout: int, max_bytes: int) -> RawExecutionResult:
    """Drain output continuously with bounded in-memory retention and a wall timeout."""
    started = time.monotonic()
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "WSL_UTF8": "1"},
    )
    buffers = [bytearray(), bytearray()]

    def drain(stream: object, index: int) -> None:
        if stream is None:
            return
        # Popen streams are binary readers; no executable or model-controlled shell.
        from typing import BinaryIO, cast

        reader = cast(BinaryIO, stream)
        with reader:
            while chunk := reader.read(4096):
                remaining = max_bytes - len(buffers[index])
                if remaining > 0:
                    buffers[index].extend(chunk[:remaining])

    readers = [
        threading.Thread(target=drain, args=(stream, i), daemon=True)
        for i, stream in enumerate((process.stdout, process.stderr))
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=5)
    for reader in readers:
        reader.join(timeout=2)
    return RawExecutionResult(
        exit_code=-1 if timed_out else process.returncode,
        stdout=buffers[0].decode("utf-8", errors="replace"),
        stderr=buffers[1].decode("utf-8", errors="replace"),
        duration=time.monotonic() - started,
        status="TIMEOUT" if timed_out else "COMPLETED",
        timeout_reason="wall_clock" if timed_out else None,
    )


class DockerRuntime:
    """One offline non-root container per run; never fall back to host execution."""

    def __init__(self, inputs: Path, workspace: Path, settings: SandboxSettings) -> None:
        self.inputs = inputs.resolve()
        self.workspace = workspace.resolve()
        self.settings = settings
        self.name = f"ctf-forge-{uuid4().hex}"
        self.docker = shutil.which("docker") or "docker"
        self.prefix = [self.docker]
        if settings.wsl_distro and os.name == "nt":
            self.prefix = docker_command(settings)
        self.running = False

    def create_argv(self) -> list[str]:
        for path in (self.inputs, self.workspace):
            if "," in str(path):
                raise ForgeError("Docker mount paths must not contain commas")
        return [
            *self.prefix,
            "run",
            "--detach",
            "--rm",
            "--init",
            "--name",
            self.name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "10001:10001",
            "--memory",
            f"{self.settings.memory_mb}m",
            "--cpus",
            str(self.settings.cpus),
            "--pids-limit",
            str(self.settings.pids_limit),
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m,mode=1777",
            "--mount",
            f"type=bind,source={mount_path(self.inputs, self.settings)},target=/input,readonly",
            "--mount",
            f"type=bind,source={mount_path(self.workspace, self.settings)},target=/work",
            "--workdir",
            "/work",
            self.settings.image,
            "sleep",
            str(self.settings.lifetime_seconds),
        ]

    def create(self) -> None:
        self.prefix = docker_command(self.settings)
        self.workspace.mkdir(parents=True, exist_ok=True)
        # This dedicated run directory must be writable by container uid 10001 on Linux too.
        self.workspace.chmod(0o777)
        if not self.inputs.is_dir():
            raise ForgeError("Input directory does not exist")
        result = bounded_run(self.create_argv(), 30, 4096)
        if not result.success:
            self.destroy()
            raise ForgeError("Docker container creation failed; check engine and analysis image")
        self.running = True

    def execute(self, argv: list[str]) -> RawExecutionResult:
        if not self.running:
            raise ForgeError("Sandbox is not running")
        if not argv or any("\x00" in arg for arg in argv):
            raise ForgeError("Invalid execution argv")
        result = bounded_run(
            [*self.prefix, "exec", "--workdir", "/work", self.name, *argv],
            self.settings.command_timeout_seconds,
            self.settings.max_output_bytes,
        )
        if result.status == "TIMEOUT":
            # Killing docker exec's host client alone does not kill the container process.
            self.destroy()
        return result

    def destroy(self) -> None:
        result = bounded_run([*self.prefix, "rm", "--force", self.name], 10, 4096)
        self.running = False
        if not result.success and "No such container" not in result.stderr:
            raise ForgeError(f"Sandbox cleanup failed; check Docker container {self.name}")
