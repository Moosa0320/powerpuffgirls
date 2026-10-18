"""Text-to-speech interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from harness.providers.base import Provider, Result, safe_call


class TTSProvider(Provider, ABC):
    name = "tts"

    @abstractmethod
    def _speak(self, text: str, lang: str) -> bytes: ...

    def speak(self, text: str, lang: str = "ur") -> Result[bytes]:
        return safe_call(self.name, self._speak, text, lang)