import pytest
from pydantic import ValidationError

from ctf_forge.core.models import ChallengeSpec, ExecResult, FlagCandidate, TaskRecord


def challenge() -> ChallengeSpec:
    return ChallengeSpec(
        challenge_id="sample-01",
        name="Test",
        description="Test input",
        files=["test.elf"],
        scope={"authorized": True},
    )


@pytest.mark.parametrize("identifier", ["../escape", "/tmp/elf", "x/y", "a b", "", "x" * 81])
def test_reject_unsafe_identifiers(identifier: str) -> None:
    data = challenge().model_dump()
    data["challenge_id"] = identifier
    with pytest.raises(ValidationError):
        ChallengeSpec.model_validate(data)


@pytest.mark.parametrize("authorized", [False, None, "true", 1])
def test_scope_must_be_explicit_boolean(authorized: object) -> None:
    data = challenge().model_dump()
    data["scope"] = {"authorized": authorized}
    with pytest.raises(ValidationError):
        ChallengeSpec.model_validate(data)


def test_confidence_cannot_imply_verified_or_success() -> None:
    candidate = FlagCandidate(value="flag{guess}", source="model", confidence=1)
    assert candidate.status == "candidate"
    with pytest.raises(ValidationError):
        TaskRecord(challenge=challenge(), candidate_flags=[candidate], status="succeeded")


@pytest.mark.parametrize("status", ["local_verified", "platform_accepted"])
def test_verified_status_needs_evidence(status: str) -> None:
    with pytest.raises(ValidationError):
        FlagCandidate.model_validate({"value": "flag{x}", "source": "test", "status": status})


def test_verified_flag_must_match_candidate() -> None:
    candidate = FlagCandidate(
        value="flag{right}",
        source="validator",
        status="local_verified",
        verification_evidence="validator exit_code=0; artifact sha256=example",
    )
    record = TaskRecord(
        challenge=challenge(),
        candidate_flags=[candidate],
        verified_flag="flag{right}",
        status="succeeded",
    )
    assert record.status == "succeeded"
    with pytest.raises(ValidationError):
        TaskRecord(
            challenge=challenge(),
            candidate_flags=[candidate],
            verified_flag="flag{wrong}",
            status="succeeded",
        )


def test_tool_result_preserves_timeout_and_rejects_negative_time() -> None:
    result = ExecResult(exit_code=None, stdout="partial", stderr="", duration_ms=10, timed_out=True)
    assert result.model_dump()["timed_out"] is True
    with pytest.raises(ValidationError):
        ExecResult(exit_code=0, stdout="", stderr="", duration_ms=-1)
