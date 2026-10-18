"""In-memory fakes for tests and offline demos. No network."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.llm.base import LLMProvider, LLMReply
from harness.providers.base import ProviderResponseError
from harness.stt.base import STTProvider
from harness.tts.base import TTSProvider
from harness.vision.base import VisionProvider


class FakeLLM(LLMProvider):
    """Returns scripted replies in order. A reply may be a str, an LLMReply or an Exception."""

    name = "llm.fake"

    def __init__(self, replies: list[Any] | None = None, env: Mapping[str, str] | None = None) -> None:
        super().__init__(env or {})
        self.replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []

    def _chat(self, messages, json_schema, tools) -> LLMReply:  # type: ignore[override]
        self.calls.append({"messages": list(messages), "json_schema": json_schema, "tools": tools})
        if not self.replies:
            raise ProviderResponseError("fake LLM has no scripted replies left")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, LLMReply):
            return reply
        return LLMReply(content=reply, raw_message={"role": "assistant", "content": reply})


class FakeSTT(STTProvider):
    name = "stt.fake"

    def __init__(self, text: str = "", fail: bool = False, env: Mapping[str, str] | None = None) -> None:
        super().__init__(env or {})
        self.text, self.fail = text, fail

    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str:
        if self.fail:
            raise ProviderResponseError("fake STT failure")
        return self.text


class FakeVision(VisionProvider):
    name = "vision.fake"

    def __init__(self, observation: dict[str, Any] | None = None, env: Mapping[str, str] | None = None) -> None:
        super().__init__(env or {})
        self.observation = observation or {}

    def _observe(self, image: bytes) -> dict[str, Any]:
        return dict(self.observation)


class FakeTTS(TTSProvider):
    name = "tts.fake"

    def _speak(self, text: str, lang: str) -> bytes:
        return text.encode("utf-8")