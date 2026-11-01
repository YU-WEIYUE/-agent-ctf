import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from ctf_forge._vendor.boxpwnr.executors.base_executor import RawExecutionResult
from ctf_forge.cli import app
from ctf_forge.config import Settings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.workflow.graph import run_autonomous
from ctf_forge.workflow.session import Session, task_lock


@pytest.fixture
def fake_docker(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(argv: list[str], timeout: int, max_bytes: int) -> RawExecutionResult:
        calls.append(argv)
        return RawExecutionResult(0, '{"bits":64,"header":{},"sections":[],"symbols":[]}', "", 0)

    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.bounded_run", run)
    monkeypatch.setattr("ctf_forge.sandbox.docker_runtime.shutil.which", lambda _: "docker")
    return calls


def new_session(tmp_path: Path, answer: bool = True) -> Session:
    binary = tmp_path / "fixture"
    binary.write_bytes(b"\x7fELF fixture only")
    answer_file = tmp_path / "gold.txt"
    answer_file.write_text("flag{private_gold}", encoding="utf-8")
    return Session.create(
        tmp_path, Settings(), binary, "Test fixture", answer_file if answer else None
    )


def test_autonomous_real_graph_checkpoint_and_verifier(
    tmp_path: Path,
    fake_docker: list[list[str]],
) -> None:
    session = new_session(tmp_path)

    class Client:
        count = 0

        def invoke(self, messages: Any, tokens_left: int, seconds_left: float) -> AIMessage:
            self.count += 1
            assert "private_gold" not in repr(messages)
            call = (
                {"name": "strings", "args": {}}
                if self.count == 1
                else {
                    "name": "submit_flag",
                    "args": {"value": "flag{private_gold}"},
                }
            )
            return AIMessage(
                content="",
                tool_calls=[{**call, "id": f"call{self.count}"}],
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )

    run_autonomous(session, Client())
    assert session.record.status == "succeeded"
    assert session.record.llm_calls == 2
    assert session.record.tokens == 30
    assert session.record.candidate_flags[-1].status == "local_verified"
    assert fake_docker[-1][1:3] == ["rm", "--force"]
    assert (tmp_path / ".data/checkpoints.sqlite3").stat().st_size > 0
    report = json.loads(Path(session.record.report_path).read_text())
    assert report["task"]["verified_flag"] == "flag{private_gold}"


def test_no_answer_cannot_self_certify(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path, answer=False)
    session.prepare()
    result = session.apply("submit_flag", {"value": "flag{anything}"})
    assert result["valid"] is False
    assert session.record.status == "running"
    assert session.record.candidate_flags[-1].status == "candidate"
    session.finish("no_validator")
    assert session.record.status == "partial"


def test_wrong_answer_then_correct(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path)
    session.prepare()
    session.apply("submit_flag", {"value": "flag{wrong}"})
    assert session.record.candidate_flags[-1].status == "rejected"
    session.apply("submit_flag", {"value": "flag{private_gold}"})
    assert session.record.status == "succeeded"
    session.finish("verified")


def test_gold_tampering_is_detected(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path)
    session.prepare()
    session.answer_file.write_text("flag{changed}")
    with pytest.raises(ForgeError, match="changed"):
        session.apply("submit_flag", {"value": "flag{changed}"})
    session.finish("tampered", failed=True)


def test_original_limits_survive_config_changes(
    tmp_path: Path, fake_docker: list[list[str]]
) -> None:
    session = new_session(tmp_path)
    session.settings.agent.max_tool_calls = 2
    session.save()
    loaded = Session.load(tmp_path, Settings(), session.record.task_id)
    assert loaded.settings.agent.max_tool_calls == 2


def test_lock_prevents_concurrent_steps(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    with task_lock(tmp_path, session.record.task_id):
        with pytest.raises(ForgeError, match="already in use"):
            with task_lock(tmp_path, session.record.task_id):
                pass


def test_model_failure_reports_and_cleans(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path)

    class BrokenClient:
        def invoke(self, *args: Any) -> AIMessage:
            raise RuntimeError("sensitive-api-body-must-not-be-logged")

    with pytest.raises(RuntimeError):
        run_autonomous(session, BrokenClient())
    assert session.record.status == "failed"
    assert not session.runtime.running
    report = Path(session.record.report_path).read_text()
    assert "sensitive-api-body" not in report


def test_external_cli_roundtrip(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    binary = tmp_path / "fixture"
    binary.write_bytes(b"\x7fELF fixture")
    gold = tmp_path / "answer"
    gold.write_text("flag{private_gold}")
    runner = CliRunner()
    prefix = ["--project", str(tmp_path)]
    started = runner.invoke(
        app, [*prefix, "solve", str(binary), "--mode", "external", "--answer-file", str(gold)]
    )
    assert started.exit_code == 0, started.output
    task_id = json.loads(started.output)["task_id"]
    assert runner.invoke(app, [*prefix, "observe", task_id]).exit_code == 0
    action = tmp_path / "action.json"
    action.write_text(
        json.dumps({"tool": "submit_flag", "arguments": {"value": "flag{private_gold}"}})
    )
    stepped = runner.invoke(app, [*prefix, "step", task_id, "--action", str(action)])
    assert stepped.exit_code == 0, stepped.output
    assert json.loads(stepped.output)["task"]["status"] == "succeeded"
    report = runner.invoke(app, [*prefix, "report", task_id])
    assert json.loads(report.output)["task"]["status"] == "succeeded"


def test_budget_stops_before_extra_tool(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path)
    session.settings.agent.max_tool_calls = 1
    session.prepare()
    session.apply("strings", {})
    session.apply("python", {"code": "print(1)"})
    assert session.record.tool_calls == 1
    assert session.record.stop_reason == "tool_budget"
    assert not session.runtime.running


def test_changed_staged_input_cannot_resume(tmp_path: Path, fake_docker: list[list[str]]) -> None:
    session = new_session(tmp_path)
    copied = session.directory / "input/challenge"
    copied.chmod(0o666)
    copied.write_bytes(b"changed")
    with pytest.raises(ForgeError, match="Staged input has changed"):
        Session.load(tmp_path, Settings(), session.record.task_id)


def test_cleanup_failure_is_not_a_success(
    tmp_path: Path,
    fake_docker: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = new_session(tmp_path)
    session.prepare()
    session.apply("submit_flag", {"value": "flag{private_gold}"})
    assert session.record.status == "succeeded"

    def broken_cleanup() -> None:
        raise ForgeError("test cleanup failure")

    monkeypatch.setattr(session.runtime, "destroy", broken_cleanup)
    session.finish("verified")
    assert session.record.status == "failed"
    assert "cleanup_required" in session.record.stop_reason


def test_final_allowed_model_call_can_still_verify(
    tmp_path: Path,
    fake_docker: list[list[str]],
) -> None:
    session = new_session(tmp_path)
    session.settings.agent.max_llm_calls = 1

    class OneCall:
        def invoke(self, *args: Any) -> AIMessage:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "submit_flag",
                        "args": {"value": "flag{private_gold}"},
                        "id": "last",
                    }
                ],
            )

    run_autonomous(session, OneCall())
    assert session.record.status == "succeeded"
    assert session.record.llm_calls == 1
