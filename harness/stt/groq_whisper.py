"""Groq-hosted Whisper (open-weight model, hosted inference). Optional."""
from __future__ import annotations

from harness.providers.base import GROQ_BASE, ProviderResponseError
from harness.stt.base import MAX_AUDIO_BYTES, STTProvider


class GroqWhisperSTT(STTProvider):
    name = "stt.groq_whisper"

    def available(self) -> bool:
        return bool(self.env.get("GROQ_API_KEY")) and bool(self.env.get("GROQ_STT_MODEL"))

    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str:
        import httpx

        if len(audio) > MAX_AUDIO_BYTES:
            raise ProviderResponseError("audio exceeds the 30 s clip limit")
        r = httpx.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.env['GROQ_API_KEY']}"},
            data={
                "model": self.env["GROQ_STT_MODEL"],
                "language": language,
                "prompt": initial_prompt,
                "response_format": "json",
            },
            files={"file": ("clip.webm", audio, "audio/webm")},
            timeout=60,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"groq stt status {r.status_code}")
        return str(r.json().get("text", "")).strip()