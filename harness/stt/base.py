"""Speech-to-text interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness.providers.base import Provider, Result, safe_call

MAX_AUDIO_SECONDS = 30
MAX_AUDIO_BYTES = 2_000_000  # generous bound for a 30 s compressed clip
AGRI_PROMPT = "urea, DAP, tomato, pani, spray, bori, tanki, khad, patta peela, gandum, kapas"


class STTProvider(Provider, ABC):
    name = "stt"

    @abstractmethod
    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str: ...

    def transcribe(
        self, audio: bytes, language: str = "ur", initial_prompt: str = AGRI_PROMPT
    ) -> Result[str]:
        return safe_call(self.name, self._transcribe, audio, language, initial_prompt)