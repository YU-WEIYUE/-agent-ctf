"""Isolated fixtures; never use user credentials or the project database."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("CTF_FORGE_"):
            monkeypatch.delenv(key)
