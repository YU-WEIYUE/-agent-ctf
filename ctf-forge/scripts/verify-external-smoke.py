"""Scripted CLI integration harness for the ten generated fixtures, not a general solver."""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def command(arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        ["uv", "run", "ctf-forge", *arguments],
        cwd=ROOT,
        capture_output=True,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stdout.decode("utf-8", errors="replace")[:500])
    data: dict[str, Any] = json.loads(result.stdout)
    return data


def main() -> None:
    manifest = ROOT / "challenges/samples/smoke/manifest.json"
    entries = json.loads(manifest.read_text())["challenges"]
    runs: list[dict[str, Any]] = []
    started = time.time()
    for entry in entries:
        task_id: str | None = None
        try:
            session = command(
                [
                    "solve",
                    str(manifest.parent / entry["binary"]),
                    "--answer-file",
                    str(manifest.parent / entry["answer"]),
                ]
            )
            task_id = session["task_id"]
            action_file = ROOT / ".data" / f"smoke-action-{task_id}.json"

            def step(
                tool: str,
                arguments: dict[str, Any],
                action_file: Path = action_file,
                task_id: str = task_id,
            ) -> dict[str, Any]:
                action_file.write_text(json.dumps({"tool": tool, "arguments": arguments}))
                return command(["step", task_id, "--action", str(action_file)])

            strings = step("strings", {})["result"]["stdout"]
            # This rule is specific to the synthetic fixture family, and never reads gold files.
            key = re.search(r"unlock-\d{2}", strings)
            if key is None:
                raise RuntimeError("No fixture key observed")
            output = step("run_binary", {"arguments": [key.group()]})["result"]["stdout"]
            candidate = re.search(r"flag\{[^{}\r\n]+\}", output)
            if candidate is None:
                raise RuntimeError("No candidate observed")
            result = step("submit_flag", {"value": candidate.group()})
            if result["task"]["status"] != "succeeded":
                raise RuntimeError("Independent verification failed")
            runs.append({"challenge": entry["id"], "task_id": task_id, "status": "succeeded"})
            print(entry["id"] + " verified", flush=True)
        except Exception as exc:
            runs.append(
                {
                    "challenge": entry["id"],
                    "task_id": task_id,
                    "status": "failed",
                    "error": type(exc).__name__,
                }
            )
            if task_id:
                command(["close", task_id])
    result = {
        "schema_version": 1,
        "kind": "scripted-external-cli-integration-not-LLM-pass-at-k",
        "passed": sum(r["status"] == "succeeded" for r in runs),
        "total": len(runs),
        "elapsed_seconds": time.time() - started,
        "runs": runs,
    }
    destination = ROOT / "reports" / f"external-smoke-{time.time_ns()}.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"passed": result["passed"], "total": result["total"], "report": str(destination)},
            ensure_ascii=True,
        )
    )
    if result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
