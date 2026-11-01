"""Fetch and digest-check the official Ubuntu image using host networking."""

import gzip
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1] / ".data" / "ubuntu-image"
root.mkdir(parents=True, exist_ok=True)
token = json.load(
    urllib.request.urlopen(
        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/ubuntu:pull",
        timeout=30,
    )
)["token"]
headers = {
    "Authorization": "Bearer " + token,
    "Accept": (
        "application/vnd.oci.image.index.v1+json, "
        "application/vnd.docker.distribution.manifest.list.v2+json, "
        "application/vnd.oci.image.manifest.v1+json"
    ),
}


def get(path):
    return urllib.request.urlopen(
        urllib.request.Request(
            "https://registry-1.docker.io/v2/library/ubuntu/" + path, headers=headers
        ),
        timeout=60,
    )


index = json.load(get("manifests/24.04"))
entry = next(
    v
    for v in index["manifests"]
    if v.get("platform", {}).get("architecture") == "amd64" and v["platform"].get("os") == "linux"
)
raw = get("manifests/" + entry["digest"]).read()
if hashlib.sha256(raw).hexdigest() != entry["digest"].split(":")[1]:
    raise ValueError("Manifest digest mismatch")
manifest = json.loads(raw)
config = get("blobs/" + manifest["config"]["digest"]).read()
if hashlib.sha256(config).hexdigest() != manifest["config"]["digest"].split(":")[1]:
    raise ValueError("Config digest mismatch")
configuration = json.loads(config)
names = []
for n, layer in enumerate(manifest["layers"]):
    compressed = root / f"{n}.gz"
    with get("blobs/" + layer["digest"]) as source, compressed.open("wb") as output:
        shutil.copyfileobj(source, output)
    if hashlib.sha256(compressed.read_bytes()).hexdigest() != layer["digest"].split(":")[1]:
        raise ValueError("Compressed layer digest mismatch")
    output = root / f"{n}.tar"
    with gzip.open(compressed, "rb") as source, output.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    if (
        hashlib.sha256(output.read_bytes()).hexdigest()
        != configuration["rootfs"]["diff_ids"][n].split(":")[1]
    ):
        raise ValueError("Uncompressed layer digest mismatch")
    names.append(output.name)
    print("verified_layer", n, output.stat().st_size, flush=True)
archive = root.parent / "ubuntu-docker.tar"
with tarfile.open(archive, "w") as tar:

    def add(name, data):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    config_name = manifest["config"]["digest"].split(":")[1] + ".json"
    add(config_name, config)
    add(
        "manifest.json",
        json.dumps(
            [{"Config": config_name, "RepoTags": ["ubuntu:24.04"], "Layers": names}]
        ).encode(),
    )
    for name in names:
        tar.add(root / name, arcname=name)
(root.parent / "ubuntu-image-source.json").write_text(
    json.dumps(
        {
            "registry": "registry-1.docker.io/library/ubuntu",
            "tag": "24.04",
            "manifest_digest": entry["digest"],
            "layers": [x["digest"] for x in manifest["layers"]],
        },
        indent=2,
    )
)
print("archive_ready", str(archive), flush=True)
