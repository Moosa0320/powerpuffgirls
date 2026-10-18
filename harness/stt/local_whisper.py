"""Local open-weight STT via faster-whisper. VAD filter trims silence."""
from __future__ import annotations

import importlib.util
import io
from typing import Any

from harness.providers.base import ProviderResponseError
from harness.stt.base import MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, STTProvider


class LocalWhisperSTT(STTProvider):
    name = "stt.local_whisper"
    _model: Any = None

    def available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _get_model(self) -> Any:
        if LocalWhisperSTT._model is None:
            from faster_whisper import WhisperModel

            size = self.env.get("WHISPER_MODEL_SIZE", "small")
            LocalWhisperSTT._model = WhisperModel(size, device="cpu", compute_type="int8")
        return LocalWhisperSTT._model

    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str:
        if len(audio) > MAX_AUDIO_BYTES:
            raise ProviderResponseError("audio exceeds the 30 s clip limit")
        segments, info = self._get_model().transcribe(
            io.BytesIO(audio), language=language, initial_prompt=initial_prompt, vad_filter=True
        )
        if info.duration > MAX_AUDIO_SECONDS + 1:
            raise ProviderResponseError(f"audio longer than {MAX_AUDIO_SECONDS}s")
        return " ".join(s.text.strip() for s in segments).strip()