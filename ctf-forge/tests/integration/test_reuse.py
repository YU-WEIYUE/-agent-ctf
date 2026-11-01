import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from ctf_forge._vendor.boxpwnr.executors.base_executor import RawExecutionResult
from ctf_forge._vendor.boxpwnr.platforms.base_platform import BasePlatform
from ctf_forge.adapters.local import LocalReversePlatform
from ctf_forge.cli import app
from ctf_forge.config import SandboxSettings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.sandbox.docker_runtime import DockerRuntime, bounded_run
from ctf_forge.tools.analyze import inspect_binary


def test_wsl_transport_never_uses_a_host_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    from ctf_forge.sandbox import docker_runtime

    monkeypatch.setattr(docker_runtime, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(docker_runtime.shutil, "which", lambda name: name)
    command = docker_runtime.docker_command(SandboxSettings(wsl_distro="Ubuntu-22.04"))
    assert command[-2:] == ["--exec", "docker"]
    assert "--" not in command


def test_vendored_source_hashes_are_preserved() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "third_party/boxpwnr-source.json").read_text())
    assert len(manifest["files"]) == 4
    for entry in manifest["files"]:
        data = (root / entry["local_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["local_sha256"]


def test_actual_upstream_contract_and_no_ground_truth_in_prompt(tmp_path: Path) -> None:
    platform = LocalReversePlatform(tmp_path, expected_flag="flag{secret}")
    assert isinstance(platform, BasePlatform)
    target = platform.initialize_target("challenge")
    assert "flag{secret}" not in repr(target)
    assert "flag{secret}" not in platform.get_platform_prompt(target, {})
    assert platform.validate_flag("flag{wrong}", target)[:2] == (False, False)
    assert platform.validate_flag("flag{secret}", target)[:2] == (True, True)
    unknown = LocalReversePlatform(tmp_path)
    assert unknown.validate_flag("flag{anything}", target)[:2] == (False, False)


def test_container_argv_enforces_profile(tmp_path: Path) -> None:
    runtime = DockerRuntime(tmp_path / "input", tmp_path / "work", SandboxSettings())
    argv = runtime.create_argv()
    for option, value in (
        ("--network", "none"),
        ("--cap-drop", "ALL"),
        ("--user", "10001:10001"),
        ("--security-opt", "no-new-privileges:true"),
        ("--pids-limit", "128"),
    ):
        assert argv[argv.index(option) + 1] == value
    assert "--read-only" in argv
    assert not any("docker.sock" in item for item in argv)
    assert "--privileged" not in argv
    assert "--cap-add" not in argv
    assert "--env" not in argv
    assert any("target=/input,readonly" in item for item in argv)


def test_real_bounded_process_output_and_timeout() -> None:
    result = bounded_run([sys.executable, "-c", "print('x'*100000)"], 10, 512)
    assert isinstance(result, RawExecutionResult)
    assert result.success
    assert len(result.stdout.encode()) <= 512
    result = bounded_run([sys.executable, "-c", "import time; time.sleep(10)"], 1, 512)
    assert not result.success
    assert result.status == "TIMEOUT"


def test_exec_timeout_destroys_container(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = DockerRuntime(tmp_path, tmp_path / "work", SandboxSettings())
    runtime.running = True
    calls: list[list[str]] = []

    def fake_run(argv: list[str], timeout: int, max_bytes: int) -> RawExecutionResult:
        calls.append(argv)
        if "exec" in argv:
            return RawExecutionResult(-1, "", "", 0, status="TIMEOUT")
        return RawExecutionResult(0, "", "", 0)

    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.bounded_run", fake_run)
    assert runtime.execute(["file", "/input/challenge"]).status == "TIMEOUT"
    assert calls[-1][1:3] == ["rm", "--force"]
    assert not runtime.running


def test_real_docker_required_no_host_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.shutil.which", lambda _: None)
    with pytest.raises(ForgeError, match="Docker CLI missing"):
        DockerRuntime(tmp_path, tmp_path / "work", SandboxSettings()).create()


def test_inspect_uses_three_fixed_tools_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "--untrusted name"
    binary.write_bytes(b"\x7fELF fixture only")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], timeout: int, max_bytes: int) -> RawExecutionResult:
        calls.append(argv)
        return RawExecutionResult(0, "fixture output", "", 0)

    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.bounded_run", fake_run)
    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.shutil.which", lambda _: "docker")
    report = inspect_binary(binary, tmp_path, SandboxSettings())
    assert report["status"] == "static_analysis_only"
    assert set(report["tools"]) == {"file", "readelf", "strings"}
    assert all(argv[0] == "docker" for argv in calls)
    assert calls[-1][1:3] == ["rm", "--force"]
    assert not list((tmp_path / "workspaces").iterdir())


def test_agent_discovery_contract_is_json() -> None:
    result = CliRunner().invoke(app, ["capabilities"])
    assert result.exit_code == 0, result.output
    contract = json.loads(result.output)
    assert contract["schema_version"] == 1
    assert "solve" in contract["sandbox_commands"]
    assert "platform_submission" not in contract["unavailable"]
    assert "platform submit" in contract["platform_commands"]
    assert contract["instructions"] == "AGENTS.md"
