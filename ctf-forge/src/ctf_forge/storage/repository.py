"""Persist and validate complete task snapshots with parameterized SQL."""

from pathlib import Path

from ctf_forge.core.exceptions import TaskNotFound
from ctf_forge.core.models import ChallengeSpec, TaskRecord
from ctf_forge.storage.database import connect, initialize


class TaskRepository:
    def __init__(self, database: Path) -> None:
        self.database = database
        initialize(database)

    def add(self, challenge: ChallengeSpec) -> TaskRecord:
        record = TaskRecord(challenge=challenge)
        with connect(self.database) as connection:
            connection.execute(
                "INSERT INTO tasks(task_id, created_at, payload) VALUES (?, ?, ?)",
                (record.task_id, record.created_at.isoformat(), record.model_dump_json()),
            )
        return record

    def get(self, task_id: str) -> TaskRecord:
        with connect(self.database) as connection:
            row = connection.execute(
                "SELECT payload FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFound(f"Task not found: {task_id}")
        return TaskRecord.model_validate_json(row["payload"])

    def save(self, record: TaskRecord) -> None:
        validated = TaskRecord.model_validate(record.model_dump())
        with connect(self.database) as connection:
            cursor = connection.execute(
                "UPDATE tasks SET payload = ? WHERE task_id = ?",
                (validated.model_dump_json(), validated.task_id),
            )
            if cursor.rowcount != 1:
                raise TaskNotFound(f"Task not found: {validated.task_id}")

    def list(self, limit: int = 50) -> list[TaskRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with connect(self.database) as connection:
            rows = connection.execute(
                "SELECT payload FROM tasks ORDER BY created_at DESC, task_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TaskRecord.model_validate_json(row["payload"]) for row in rows]
