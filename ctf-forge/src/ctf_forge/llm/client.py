"""OpenAI-compatible tool calling with explicit request and token limits."""

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, messages_to_dict
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from ctf_forge.config import ModelSettings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.tools.registry import tool_schemas


class ModelClient:
    def __init__(self, settings: ModelSettings) -> None:
        if not settings.name or not settings.base_url:
            raise ForgeError("Model name and base_url must be configured")
        key = settings.api_key.get_secret_value() if settings.api_key else ""
        if settings.provider != "ollama" and not key:
            raise ForgeError("A model API key is required for this provider")
        self.settings = settings
        self.key = key or "ollama"

    def _deepseek(self, messages: list[BaseMessage], available: int, timeout: float) -> AIMessage:
        """Preserve DeepSeek reasoning_content across thinking/tool rounds."""
        wire: list[dict[str, Any]] = []
        for message in messages:
            role = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}[
                message.type
            ]
            item: dict[str, Any] = {"role": role, "content": message.content}
            if isinstance(message, ToolMessage):
                item["tool_call_id"] = message.tool_call_id
            if isinstance(message, AIMessage):
                if message.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["args"]),
                            },
                        }
                        for call in message.tool_calls
                    ]
                if "reasoning_content" in message.additional_kwargs:
                    item["reasoning_content"] = message.additional_kwargs["reasoning_content"]
            wire.append(item)
        kwargs: dict[str, Any] = {
            "model": self.settings.name,
            "messages": wire,
            "tools": tool_schemas(),
            "max_tokens": available,
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.thinking else "disabled"}
            },
        }
        if self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        with OpenAI(
            api_key=self.key, base_url=str(self.settings.base_url), timeout=timeout, max_retries=0
        ) as sdk:
            completion = sdk.chat.completions.create(**kwargs)
        choice = completion.choices[0].message
        calls = [
            {
                "name": call.function.name,
                "args": json.loads(call.function.arguments),
                "id": call.id,
                "type": "tool_call",
            }
            for call in (choice.tool_calls or [])
        ]
        extra = {}
        reasoning = getattr(choice, "reasoning_content", None)
        if reasoning is not None:
            extra["reasoning_content"] = reasoning
        usage = completion.usage
        return AIMessage(
            content=choice.content or "",
            tool_calls=calls,
            additional_kwargs=extra,
            usage_metadata={
                "input_tokens": usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            if usage
            else None,
        )

    def invoke(
        self, messages: list[BaseMessage], tokens_left: int, seconds_left: float
    ) -> AIMessage:
        # Byte count is a conservative input reserve for byte-tokenized compatible models.
        prompt = json.dumps(messages_to_dict(messages), ensure_ascii=False)
        reserve = len(prompt.encode()) + len(json.dumps(tool_schemas()).encode()) + 1024
        available = min(4096, tokens_left - reserve)
        if available < 128:
            raise ForgeError("Token budget has insufficient input/output headroom")
        options: dict[str, Any] = {
            "model": self.settings.name,
            "base_url": str(self.settings.base_url),
            "api_key": self.key,
            "temperature": 0,
            "timeout": min(self.settings.timeout_seconds, max(1, seconds_left)),
            "max_retries": 0,
            "max_tokens": available,
        }
        started = time.monotonic()
        for attempt in range(self.settings.max_retries + 1):
            remaining = seconds_left - (time.monotonic() - started)
            if remaining <= 0:
                raise ForgeError("Model wall-time budget exhausted")
            options["timeout"] = min(self.settings.timeout_seconds, remaining)
            try:
                if self.settings.provider == "deepseek":
                    response = self._deepseek(messages, available, options["timeout"])
                else:
                    client = ChatOpenAI(**options).bind_tools(tool_schemas())
                    response = client.invoke(messages)
            except (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError):
                if attempt == self.settings.max_retries:
                    raise
                continue
            if not isinstance(response, AIMessage):
                raise ForgeError("Unexpected model response type")
            response.response_metadata["request_attempts"] = attempt + 1
            if response.usage_metadata is None:
                response.usage_metadata = {
                    "input_tokens": reserve,
                    "output_tokens": len(str(response.content).encode()) + 64,
                    "total_tokens": reserve + len(str(response.content).encode()) + 64,
                }
                response.response_metadata["usage_estimated"] = True
            return response
        raise ForgeError("Model retry loop exhausted")
