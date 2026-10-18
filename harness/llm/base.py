"""LLM interface with tool-calling and JSON-schema support."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from harness.providers.base import Provider, Result, safe_call


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LLMReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    raw_message: dict[str, Any] | None = None  # provider-native assistant message


class LLMProvider(Provider, ABC):
    name = "llm"

    @abstractmethod
    def _chat(
        self,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None,
    ) -> LLMReply: ...

    def chat(
        self,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Result[LLMReply]:
        return safe_call(self.name, self._chat, messages, json_schema, tools)

    def tool_result_message(self, call: ToolCall, content: str) -> dict[str, Any]:
        return {"role": "tool", "content": content}