import sqlite3
from pathlib import Path

import pytest

from ctf_forge.core.exceptions import ForgeError, TaskNotFound
from ctf_forge.core.models import ChallengeSpec
from ctf_forge.storage.database import initialize
from ctf_forge.storage.repository import TaskRepository


def test_persistence_reopen_and_parameterized_lookup(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    repository = TaskRepository(path)
    spec = ChallengeSpec(
        challenge_id="one",
        name="Quote ' [bold] 测试",
        description="Test",
        files=["file"],
        scope={"authorized": True},
    )
    first = repository.add(spec)
    second = repository.add(spec)
    reopened = TaskRepository(path)
    assert reopened.get(first.task_id) == first
    assert reopened.list() == [second, first]
    with pytest.raises(TaskNotFound):
        reopened.get("' OR 1=1 --")
    assert len(reopened.list()) == 2
    with pytest.raises(ValueError):
        reopened.list(-1)


def test_unknown_schema_is_not_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(ForgeError, match="Unsupported database schema"):
        initialize(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99
