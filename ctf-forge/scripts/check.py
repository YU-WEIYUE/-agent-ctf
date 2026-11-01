"""Run the required project checks and save their real output; fail on the first error."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    ["ruff", "check", "."],
    ["ruff", "format", "--check", "."],
    ["mypy", "src/"],
    ["pytest", "-q"],
]


def main() -> None:
    logs = ROOT / ".data"
    logs.mkdir(exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    with (logs / f"verification-{day}.txt").open("w", encoding="utf-8") as log:
        for arguments in CHECKS:
            result = subprocess.run(
                ["uv", "run", *arguments],
                cwd=ROOT,
                capture_output=True,
                timeout=180,
                env={**os.environ, "PYTHONUTF8": "1"},
            )
            log.write("uv run " + " ".join(arguments) + "\n")
            log.write(result.stdout.decode("utf-8", errors="replace"))
            log.write(result.stderr.decode("utf-8", errors="replace"))
            log.write(f"exit_code={result.returncode}\n\n")
            log.flush()
            print(" ".join(arguments) + f": exit {result.returncode}", flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
