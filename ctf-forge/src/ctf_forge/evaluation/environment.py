"""Verify the actual running container, including negative isolation checks."""

import json
import tempfile
from pathlib import Path
from typing import Any

from ctf_forge.config import Settings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.sandbox.docker_runtime import DockerRuntime, bounded_run

CHECK_SCRIPT = """
import os,json,socket
def cannot_write(path):
 try:
  with open(path,'wb') as f: f.write(b'bad')
  return False
 except OSError: return True
s=socket.socket(); s.settimeout(1)
mount_points=[]
with open('/proc/self/mountinfo',encoding='utf-8') as f:
 for line in f:
  fields=line.split()
  if len(fields)>4: mount_points.append(fields[4])
out={'non_root':os.getuid()!=0,'root_read_only':cannot_write('/rootfs-test'),
 'input_read_only':cannot_write('/input/sentinel'),
 'work_writable':not cannot_write('/work/output'),
 'no_host_mount':not any(p=='/host' or p.startswith('/host/') or
                         p=='/mnt/host' or p.startswith('/mnt/host/')
                         for p in mount_points),
 'no_credentials':not any(k in os.environ for k in
  ['OPENAI_API_KEY','ANTHROPIC_API_KEY','CTFD_TOKEN']),
 'network_blocked':s.connect_ex(('1.1.1.1',443))!=0}
print(json.dumps(out))
"""


def check_environment(root: Path, settings: Settings) -> dict[str, Any]:
    location = root / "workspaces"
    location.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="selftest-", dir=location) as temporary:
        directory = Path(temporary)
        inputs = directory / "input"
        inputs.mkdir()
        (inputs / "sentinel").write_text("read-only")
        (inputs / "sentinel").chmod(0o666)
        runtime = DockerRuntime(inputs, directory / "work", settings.sandbox)
        runtime.create()
        try:
            result = runtime.execute(["python3", "-I", "-c", CHECK_SCRIPT])
            if not result.success:
                raise ForgeError("Container isolation probe failed to execute")
            checks = json.loads(result.stdout)
            inspected = bounded_run([*runtime.prefix, "inspect", runtime.name], 10, 65536)
            container_info = json.loads(inspected.stdout)[0]
            image_id = container_info["Image"]
            config = container_info["HostConfig"]
            checks["readonly_profile"] = config["ReadonlyRootfs"] is True
            checks["no_new_privileges"] = "no-new-privileges:true" in config["SecurityOpt"]
            checks["memory_limited"] = config["Memory"] == settings.sandbox.memory_mb * 1024 * 1024
            checks["cpu_limited"] = config["NanoCpus"] == int(settings.sandbox.cpus * 1e9)
            checks["pids_limited"] = config["PidsLimit"] == settings.sandbox.pids_limit
            checks["capabilities_dropped"] = config["CapDrop"] == ["ALL"]
            runtime.settings = settings.sandbox.model_copy(update={"command_timeout_seconds": 1})
            timeout = runtime.execute(["python3", "-I", "-c", "import time; time.sleep(3)"])
            checks["timeout_stops_container"] = timeout.status == "TIMEOUT" and not runtime.running
        finally:
            if runtime.running:
                runtime.destroy()
        return {
            "schema_version": 1,
            "passed": all(checks.values()),
            "checks": checks,
            "image_id": image_id,
            "sandbox_settings": settings.sandbox.model_dump(),
        }
