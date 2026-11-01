"""Fixed static-tool argv; untrusted attachments only enter a Docker input mount."""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from ctf_forge.config import SandboxSettings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.sandbox.docker_runtime import DockerRuntime


def inspect_binary(binary: Path, root: Path, settings: SandboxSettings) -> dict[str, Any]:
    if not binary.is_file():
        raise ForgeError("Attachment must be an existing regular file")
    if binary.stat().st_size > 64 * 1024 * 1024:
        raise ForgeError("Attachment exceeds 64 MiB")
    runs = root / "workspaces"
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inspect-", dir=runs) as temporary:
        location = Path(temporary)
        inputs = location / "input"
        inputs.mkdir()
        # Fixed neutral filename prevents model-controlled paths/options and name collisions.
        shutil.copyfile(binary, inputs / "challenge")
        runtime = DockerRuntime(inputs, location / "work", settings)
        runtime.create()
        results: dict[str, Any] = {}
        try:
            for name, argv in (
                ("file", ["file", "--", "/input/challenge"]),
                ("readelf", ["readelf", "-h", "-S", "-s", "-r", "-d", "/input/challenge"]),
                ("strings", ["strings", "-a", "-n", "4", "/input/challenge"]),
            ):
                result = runtime.execute(argv)
                results[name] = vars(result)
                if not result.success:
                    raise ForgeError(f"Analysis tool {name} failed ({result.status})")
        finally:
            if runtime.running:
                runtime.destroy()
        return {"status": "static_analysis_only", "tools": results, "verified_flag": None}
