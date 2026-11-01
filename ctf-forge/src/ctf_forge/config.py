"""Validated project-local YAML with environment and dotenv overrides."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from ctf_forge.core.exceptions import ForgeError
from ctf_forge.core.models import StrictModel


class AgentSettings(StrictModel):
    max_seconds: int = Field(default=600, ge=1, le=86400)
    max_tool_calls: int = Field(default=30, ge=1, le=1000)
    max_llm_calls: int = Field(default=15, ge=1, le=1000)
    max_tokens: int = Field(default=100000, ge=1, le=10000000)
    max_stalled_steps: int = Field(default=3, ge=1, le=100)


class ModelSettings(StrictModel):
    provider: Literal["openai", "deepseek", "ollama"] = "openai"
    thinking: bool = False
    reasoning_effort: Literal["low", "high", "max"] | None = None
    name: str | None = None
    base_url: HttpUrl | None = None
    api_key: SecretStr | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)


class SandboxSettings(StrictModel):
    wsl_distro: str | None = None
    image: str = "ctf-forge-reverse:0.1"
    network: Literal["none"] = "none"
    read_only: Literal[True] = True
    non_root: Literal[True] = True
    memory_mb: int = Field(default=1024, ge=64, le=8192)
    cpus: float = Field(default=1.0, gt=0, le=8)
    pids_limit: int = Field(default=128, ge=1, le=512)
    command_timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_output_bytes: int = Field(default=65536, ge=256, le=1048576)
    lifetime_seconds: int = Field(default=900, ge=30, le=86400)


class PlatformSettings(StrictModel):
    """Host-side competition platform; the sandbox never reaches it."""

    base_url: HttpUrl | None = None
    auth_token: SecretStr | None = None
    session_file: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        min_length=10,
        max_length=300,
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CTF_FORGE_",
        env_nested_delimiter="__",
        extra="forbid",
        env_file_encoding="utf-8-sig",
        hide_input_in_errors=True,
    )
    agent: AgentSettings = Field(default_factory=AgentSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    platform: PlatformSettings = Field(default_factory=PlatformSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, dotenv_settings, init_settings, file_secret_settings


def load_settings(root: Path) -> Settings:
    """Priority: process environment > project .env > YAML > built-in defaults."""
    values: dict[str, Any] = {}
    for key, filename in (
        ("agent", "agent.yaml"),
        ("model", "models.yaml"),
        ("sandbox", "sandbox.yaml"),
        ("platform", "platform.yaml"),
    ):
        path = root / "configs" / filename
        if path.exists():
            if path.stat().st_size > 65536:
                raise ForgeError(f"Configuration too large: {path}")
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            except yaml.YAMLError as exc:
                raise ForgeError(f"Invalid YAML in {path.name}") from exc
            if not isinstance(data, dict):
                raise ForgeError(f"Expected mapping in {path.name}")
            values[key] = data
    values["_env_file"] = root / ".env"
    return Settings(**values)
