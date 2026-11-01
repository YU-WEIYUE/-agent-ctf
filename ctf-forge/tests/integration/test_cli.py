import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ctf_forge.cli import app
from ctf_forge.config import Settings

runner = CliRunner()


def test_registration_cli_roundtrip(tmp_path: Path) -> None:
    spec = tmp_path / "challenge.json"
    (tmp_path / "attachment").write_text("Untrusted data, never executed", encoding="utf-8")
    spec.write_text(
        json.dumps(
            {
                "challenge_id": "demo",
                "name": "Test",
                "category": "reverse",
                "description": "Registration test",
                "files": ["attachment"],
                "scope": {"authorized": True},
            }
        ),
        encoding="utf-8-sig",
    )
    prefix = ["--project", str(tmp_path)]
    assert runner.invoke(app, prefix + ["init"]).exit_code == 0
    assert runner.invoke(app, prefix + ["init"]).exit_code == 0
    result = runner.invoke(app, prefix + ["task", "add", str(spec)])
    assert result.exit_code == 0, result.output
    task_id = result.output.strip()
    shown = runner.invoke(app, prefix + ["task", "show", task_id])
    assert shown.exit_code == 0, shown.output
    data = json.loads(shown.output)
    assert data["status"] == "pending"
    assert data["challenge"]["files"] == [str((tmp_path / "attachment").resolve())]
    assert data["tool_calls"] == data["llm_calls"] == data["tokens"] == 0
    assert runner.invoke(app, prefix + ["task", "list"]).exit_code == 0
    report = runner.invoke(app, prefix + ["report", task_id])
    assert report.exit_code == 0
    assert json.loads(report.output)["kind"] == "task_snapshot"
    missing = runner.invoke(app, prefix + ["task", "show", "missing"])
    assert missing.exit_code != 0
    assert "Task not found" in missing.output


def test_missing_attachment_not_saved(tmp_path: Path) -> None:
    spec = tmp_path / "challenge.json"
    spec.write_text(
        json.dumps(
            {
                "challenge_id": "demo",
                "name": "Test",
                "description": "Test",
                "files": ["missing"],
                "scope": {"authorized": True},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["--project", str(tmp_path), "task", "add", str(spec)])
    assert result.exit_code != 0
    assert not (tmp_path / ".data/tasks.sqlite3").exists()


@pytest.mark.parametrize("command", [["inspect", "not-real.elf"], ["solve", "not-real.elf"]])
def test_unimplemented_execution_refuses(command: list[str], tmp_path: Path) -> None:
    result = runner.invoke(app, ["--project", str(tmp_path), *command])
    assert result.exit_code == 2
    assert not (tmp_path / ".data").exists()


def test_secret_not_in_config_output_or_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTF_FORGE_MODEL__API_KEY", "do-not-print-this")
    args = ["--project", str(tmp_path), "config-check"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert "do-not-print-this" not in result.output
    monkeypatch.setenv("CTF_FORGE_MODEL__TIMEOUT_SECONDS", "secret-invalid-number")
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "secret-invalid-number" not in result.output
    assert "do-not-print-this" not in result.output


def test_doctor_missing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ctf_forge.cli.load_settings", lambda _: Settings())
    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.shutil.which", lambda _: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "Docker CLI missing" in result.output


@pytest.mark.parametrize("kind", ["timeout", "windows", "linux", "offline"])
def test_doctor_daemon_cases(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ctf_forge.cli.load_settings", lambda _: Settings())
    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.shutil.which", lambda _: "docker")

    def probe(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 10
        assert "shell" not in kwargs
        if kind == "timeout":
            raise subprocess.TimeoutExpired("docker", 10)
        return subprocess.CompletedProcess(
            args=[],
            returncode=1 if kind == "offline" else 0,
            stdout=kind,
            stderr="",
        )

    monkeypatch.setattr("ctf_forge.cli.subprocess.run", probe)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == (0 if kind == "linux" else 1)


def test_help_and_version_without_database(tmp_path: Path) -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["--version"]).exit_code == 0
    assert not (tmp_path / ".data").exists()
