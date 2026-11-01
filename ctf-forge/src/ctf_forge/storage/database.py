"""Schema initialization; database versions fail closed."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ctf_forge.core.exceptions import ForgeError


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path) -> None:
    with connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in {0, 1}:
            raise ForgeError(f"Unsupported database schema: {version}")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        connection.execute("PRAGMA user_version = 1")
