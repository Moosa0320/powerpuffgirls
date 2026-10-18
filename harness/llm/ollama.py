"""Local open-weight LLM via Ollama (e.g. Qwen). Structured outputs via `format`."""
from __future__ import annotations

from typing import Any

from harness.llm.base import LLMProvider, LLMReply, ToolCall
from harness.providers.base import ProviderResponseError


class OllamaLLM(LLMProvider):
    name = "llm.ollama"

    def _base(self) -> str:
        return self.env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    def _model(self) -> str:
        return self.env.get("OLLAMA_LLM_MODEL", "qwen2.5")

    def _chat(self, messages, json_schema, tools) -> LLMReply:  # type: ignore[override]
        import httpx

        body: dict[str, Any] = {
            "model": self._model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if json_schema is not None:
            body["format"] = json_schema
        if tools:
            body["tools"] = tools
        r = httpx.post(f"{self._base()}/api/chat", json=body, timeout=120)
        if r.status_code != 200:
            raise ProviderResponseError(f"ollama status {r.status_code}")
        msg = r.json().get("message", {}) or {}
        calls = [
            ToolCall(name=c["function"]["name"], arguments=c["function"].get("arguments") or {})
            for c in msg.get("tool_calls") or []
        ]
        return LLMReply(content=msg.get("content", "") or "", tool_calls=calls,
                        model=self._model(), raw_message=msg or None)

    def tool_result_message(self, call: ToolCall, content: str) -> dict[str, Any]:
        return {"role": "tool", "content": content, "tool_name": call.name}