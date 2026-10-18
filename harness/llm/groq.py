"""Groq-hosted open-weight LLM (OpenAI-compatible API). Optional cloud backend."""
from __future__ import annotations

import json
from typing import Any

from harness.llm.base import LLMProvider, LLMReply, ToolCall
from harness.providers.base import GROQ_BASE, ProviderResponseError


class GroqLLM(LLMProvider):
    name = "llm.groq"

    def available(self) -> bool:
        return bool(self.env.get("GROQ_API_KEY")) and bool(self.env.get("GROQ_LLM_MODEL"))

    def _chat(self, messages, json_schema, tools) -> LLMReply:  # type: ignore[override]
        import httpx

        model = self.env["GROQ_LLM_MODEL"]
        msgs = list(messages)
        body: dict[str, Any] = {"model": model, "temperature": 0}
        if tools:
            body["tools"] = tools
        elif json_schema is not None:
            body["response_format"] = {"type": "json_object"}
            msgs = [{"role": "system", "content": "Return only JSON matching this JSON schema: "
                     + json.dumps(json_schema)}] + msgs
        body["messages"] = msgs
        r = httpx.post(
            f"{GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {self.env['GROQ_API_KEY']}"},
            json=body,
            timeout=90,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"groq llm status {r.status_code}")
        choice = r.json()["choices"][0]["message"]
        calls: list[ToolCall] = []
        for c in choice.get("tool_calls") or []:
            fn = c["function"]
            args = fn.get("arguments") or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {}
            calls.append(ToolCall(name=fn["name"], arguments=parsed, id=c.get("id", "")))
        raw: dict[str, Any] = {"role": "assistant", "content": choice.get("content") or ""}
        if choice.get("tool_calls"):
            raw["tool_calls"] = choice["tool_calls"]
        return LLMReply(content=choice.get("content") or "", tool_calls=calls, model=model,
                        raw_message=raw)

    def tool_result_message(self, call: ToolCall, content: str) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": call.id, "content": content}