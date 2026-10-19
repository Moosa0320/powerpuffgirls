"""Local open-weight STT via faster-whisper (the default backend).

Silence is trimmed by faster-whisper's VAD filter (bundled Silero VAD). The clip checks run
before the model loads. faster-whisper decodes the audio and measures `info.duration` inside
`transcribe()`, but decodes segments lazily as the generator is consumed, so an over-long clip is
rejected before any segment is decoded.

Model weights: the first transcription for a WHISPER_MODEL_SIZE downloads the converted model
from the Hugging Face Hub. That can outlast the 90 s provider timeout; the call then returns a
typed timeout while the load finishes in the background, and later calls use the cached model.
"""
from __future__ import annotations

import importlib.util
import io
import threading
from typing import Any, ClassVar

from harness.stt.base import STTProvider, check_audio, check_duration, clean_transcript

DEFAULT_MODEL_SIZE = "small"


class LocalWhisperSTT(STTProvider):
    name = "stt.local_whisper"
    # One loaded model per size, shared by all instances; the lock makes each load run once.
    _models: ClassVar[dict[str, Any]] = {}
    _models_lock: ClassVar[threading.Lock] = threading.Lock()

    def available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def model_size(self) -> str:
        return (self.env.get("WHISPER_MODEL_SIZE") or "").strip() or DEFAULT_MODEL_SIZE

    def _load_model(self, size: str) -> Any:
        from faster_whisper import WhisperModel

        return WhisperModel(size, device="cpu", compute_type="int8")

    def _get_model(self) -> Any:
        size = self.model_size()
        models = LocalWhisperSTT._models
        if size not in models:
            with LocalWhisperSTT._models_lock:
                if size not in models:  # another thread may have loaded it while we waited
                    models[size] = self._load_model(size)
        return models[size]

    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str:
        check_audio(audio)
        segments, info = self._get_model().transcribe(
            io.BytesIO(audio), language=language, initial_prompt=initial_prompt, vad_filter=True
        )
        check_duration(getattr(info, "duration", None))  # before any segment is decoded
        return clean_transcript(" ".join(t for t in (s.text.strip() for s in segments) if t))
