"""Domain validation; a flag-shaped string alone never proves success."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
FlagStatus = Literal["candidate", "format_valid", "local_verified", "platform_accepted", "rejected"]
TaskStatus = Literal["pending", "running", "partial", "succeeded", "failed"]


class StrictModel(BaseModel):
    """Reject unknown fields instead of silently losing user input."""

    model_config = ConfigDict(extra="forbid")


class ChallengeSpec(StrictModel):
    challenge_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    category: Literal["reverse"] = "reverse"
    description: str = Field(max_length=100000)
    files: list[str] = Field(min_length=1, max_length=32)
    scope: dict[str, Any]

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if self.scope.get("authorized") is not True:
            raise ValueError("scope.authorized must explicitly be true")
        if any(not path.strip() for path in self.files):
            raise ValueError("attachment paths cannot be empty")
        return self


class ExecResult(StrictModel):
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)
    timed_out: bool = False
    output_truncated: bool = False


class Observation(StrictModel):
    source: str
    content: str
    artifact_path: str | None = None


class FlagCandidate(StrictModel):
    value: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: FlagStatus = "candidate"
    verification_evidence: str | None = None

    @model_validator(mode="after")
    def require_evidence(self) -> Self:
        if self.status in {"local_verified", "platform_accepted"}:
            if not self.verification_evidence or not self.verification_evidence.strip():
                raise ValueError("verified status requires verification evidence")
        return self


class TaskRecord(StrictModel):
    task_id: Identifier = Field(default_factory=lambda: uuid4().hex)
    challenge: ChallengeSpec
    status: TaskStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    candidate_flags: list[FlagCandidate] = Field(default_factory=list)
    verified_flag: str | None = None
    tool_calls: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    sandbox_id: str | None = None
    report_path: str | None = None
    stop_reason: str | None = None

    @model_validator(mode="after")
    def validate_success(self) -> Self:
        verified = any(
            f.value == self.verified_flag and f.status in {"local_verified", "platform_accepted"}
            for f in self.candidate_flags
        )
        if self.verified_flag is not None and not verified:
            raise ValueError("verified_flag needs a matching verified candidate")
        if self.status == "succeeded" and not verified:
            raise ValueError("task success needs verified flag evidence")
        return self
