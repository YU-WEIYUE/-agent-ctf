import json
from pathlib import Path

from ctf_forge.core.events import create_logger


def test_json_logs_redact_nested_secrets_without_duplicate_handlers(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    logger = create_logger(path)
    logger.info("first", api_key="hidden-one", details={"authorization": "hidden-two", "ok": 1})
    create_logger(path).info("second", items=[{"password": "hidden-three"}])
    content = path.read_text(encoding="utf-8")
    assert "hidden-" not in content
    rows = [json.loads(line) for line in content.splitlines()]
    assert len(rows) == 2
    assert rows[0]["details"]["ok"] == 1
    assert rows[1]["items"][0]["password"] == "[REDACTED]"
