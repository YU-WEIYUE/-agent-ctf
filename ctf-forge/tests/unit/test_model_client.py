import json
from typing import Any

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from openai import OpenAI as RealOpenAI
from pydantic import SecretStr

from ctf_forge.config import ModelSettings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.llm.client import ModelClient


def test_deepseek_http_contract_retains_reasoning_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "test-reasoning",
                            "tool_calls": [
                                {
                                    "id": "call-test",
                                    "type": "function",
                                    "function": {"name": "strings", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    def factory(**kwargs: Any) -> RealOpenAI:
        return RealOpenAI(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    monkeypatch.setattr("ctf_forge.llm.client.OpenAI", factory)
    settings = ModelSettings(
        provider="deepseek",
        name="test-model",
        base_url="https://example.test",
        api_key=SecretStr("dummy-key"),
        thinking=True,
    )
    model = ModelClient(settings)
    response = model.invoke([HumanMessage(content="Analyze")], 100000, 30)
    assert response.tool_calls[0]["name"] == "strings"
    assert response.usage_metadata["total_tokens"] == 15
    model.invoke(
        [
            HumanMessage(content="Analyze"),
            response,
            ToolMessage(content="fixture output", tool_call_id="call-test"),
        ],
        100000,
        30,
    )
    assert payloads[0]["thinking"] == {"type": "enabled"}
    assert payloads[1]["messages"][1]["reasoning_content"] == "test-reasoning"
    assert payloads[1]["messages"][1]["tool_calls"][0]["id"] == "call-test"
    assert payloads[1]["messages"][2]["tool_call_id"] == "call-test"


def test_cloud_requires_explicit_key() -> None:
    with pytest.raises(ForgeError, match="API key"):
        ModelClient(
            ModelSettings(provider="deepseek", name="test", base_url="https://example.test")
        )


def test_missing_model_fails_without_network() -> None:
    with pytest.raises(ForgeError, match="configured"):
        ModelClient(ModelSettings())
