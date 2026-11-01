from pathlib import Path

import pytest
from pydantic import ValidationError

from ctf_forge.config import load_settings
from ctf_forge.core.exceptions import ForgeError


def test_yaml_dotenv_environment_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "agent.yaml").write_text("max_tool_calls: 7\nmax_llm_calls: 8\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "CTF_FORGE_AGENT__MAX_TOOL_CALLS=9\nCTF_FORGE_MODEL__API_KEY=test-secret\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setenv("CTF_FORGE_AGENT__MAX_TOOL_CALLS", "11")
    settings = load_settings(tmp_path)
    assert settings.agent.max_tool_calls == 11
    assert settings.agent.max_llm_calls == 8
    assert settings.model.api_key is not None
    assert settings.model.api_key.get_secret_value() == "test-secret"
    assert "test-secret" not in repr(settings)
    monkeypatch.delenv("CTF_FORGE_AGENT__MAX_TOOL_CALLS")
    assert load_settings(tmp_path).agent.max_tool_calls == 9
    (tmp_path / ".env").unlink()
    assert load_settings(tmp_path).agent.max_tool_calls == 7


@pytest.mark.parametrize(
    "yaml_text",
    [
        "network: bridge",
        "read_only: false",
        "non_root: false",
        "pids_limit: 0",
        "cpus: 0",
        "unknown_setting: 1",
    ],
)
def test_invalid_sandbox_settings_fail(tmp_path: Path, yaml_text: str) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/sandbox.yaml").write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(tmp_path)


@pytest.mark.parametrize(
    "yaml_text", ["[not, a, mapping]", "!unknown invalid", "key: [unterminated"]
)
def test_malformed_yaml_rejected(tmp_path: Path, yaml_text: str) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/agent.yaml").write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ForgeError):
        load_settings(tmp_path)
