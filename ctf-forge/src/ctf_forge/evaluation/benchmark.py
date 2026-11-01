"""Ten generated, answer-separated ELF smoke tasks; not a public CTF performance claim."""

import json
import time
from pathlib import Path
from typing import Any

from ctf_forge.config import Settings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.sandbox.docker_runtime import DockerRuntime
from ctf_forge.workflow.graph import run_autonomous
from ctf_forge.workflow.session import Session, write_json


def build_samples(root: Path, settings: Settings) -> Path:
    location = root / "challenges/samples/smoke"
    source = location / "sources"
    binaries = location / "bin"
    answers = location / "answers"
    for path in (source, binaries, answers):
        path.mkdir(parents=True, exist_ok=True)
    entries = []
    for number in range(10):
        name = f"reverse_{number:02d}"
        flag = f"flag{{forge_smoke_{number:02d}_verified}}"
        key = f"unlock-{number:02d}"
        salt = number + 17
        data = [b ^ salt for b in flag.encode()]
        program = (
            "#include <stdio.h>\n#include <string.h>\n"
            f"unsigned char cipher[] = {{{','.join(map(str, data))}}};\n"
            f'int main(int argc,char **argv){{if(argc!=2||strcmp(argv[1],"{key}"))'
            '{puts("Find the key and pass it as argv[1]");return 1;}\n'
            f"for(unsigned i=0;i<sizeof(cipher);i++)putchar(cipher[i]^{salt});"
            "putchar(10);return 0;}\n"
        )
        (source / f"{name}.c").write_text(program, encoding="utf-8")
        (answers / f"{name}.txt").write_text(flag, encoding="utf-8")
        entries.append(
            {
                "id": name,
                "binary": f"bin/{name}",
                "answer": f"answers/{name}.txt",
                "difficulty": "synthetic-easy",
                "description": "Find the key and recover the flag from this ELF.",
            }
        )
    runtime = DockerRuntime(source, binaries, settings.sandbox)
    runtime.create()
    try:
        for entry in entries:
            name = entry["id"]
            result = runtime.execute(["gcc", "-O0", "-o", f"/work/{name}", f"/input/{name}.c"])
            if not result.success:
                raise ForgeError(f"Fixture compilation failed: {name}")
    finally:
        if runtime.running:
            runtime.destroy()
    destination = location / "manifest.json"
    write_json(
        destination,
        {
            "schema_version": 1,
            "kind": "synthetic-smoke-not-public-benchmark",
            "challenges": entries,
        },
    )
    return destination


def run_benchmark(
    root: Path, settings: Settings, manifest: Path, attempts: int, limit: int
) -> dict[str, Any]:
    if attempts not in {1, 3}:
        raise ForgeError("Benchmark attempts must be 1 or 3")
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    entries = data["challenges"][:limit]
    if not entries:
        raise ForgeError("No benchmark challenges")
    started = time.time()
    runs: list[dict[str, Any]] = []
    for entry in entries:
        for attempt in range(attempts):
            session = Session.create(
                root,
                settings.model_copy(deep=True),
                (manifest.parent / entry["binary"]).resolve(),
                entry["description"],
                (manifest.parent / entry["answer"]).resolve(),
            )
            try:
                run_autonomous(session)
            except Exception:
                # The session has already persisted a failure report; continue to the next task.
                pass
            runs.append(
                {
                    "challenge_id": entry["id"],
                    "attempt": attempt + 1,
                    "task_id": session.record.task_id,
                    "status": session.record.status,
                }
            )
            write_json(root / ".data/benchmark-in-progress.json", {"runs": runs})
    first_pass = sum(
        any(
            r["challenge_id"] == e["id"] and r["attempt"] == 1 and r["status"] == "succeeded"
            for r in runs
        )
        for e in entries
    )
    all_pass = sum(
        any(r["challenge_id"] == e["id"] and r["status"] == "succeeded" for r in runs)
        for e in entries
    )
    reports = [json.loads((root / "reports" / f"{r['task_id']}.json").read_text()) for r in runs]
    observations = [o for r in reports for o in r["observations"]]
    result = {
        "schema_version": 1,
        "kind": data.get("kind", "user_benchmark"),
        "challenge_count": len(entries),
        "attempts_per_challenge": attempts,
        "pass_at_1": first_pass / len(entries),
        "pass_at_3": all_pass / len(entries) if attempts == 3 else None,
        "mean_seconds_per_attempt": sum(r["elapsed_seconds"] for r in reports) / len(reports),
        "tokens": sum(r["task"]["tokens"] for r in reports),
        "model_cost": 0.0 if settings.model.provider == "ollama" else None,
        "model_cost_note": "local inference API fee only; hardware/electricity excluded"
        if settings.model.provider == "ollama"
        else "provider billing not supplied",
        "tool_execution_success_rate": sum(o.get("exit_code") == 0 for o in observations)
        / len(observations)
        if observations
        else None,
        "rejected_candidates": sum(
            f["status"] == "rejected" for r in reports for f in r["task"]["candidate_flags"]
        ),
        "elapsed_seconds": time.time() - started,
        "runs": runs,
    }
    destination = root / "reports" / f"benchmark-{time.time_ns()}.json"
    write_json(destination, result)
    result["report_path"] = str(destination)
    return result
