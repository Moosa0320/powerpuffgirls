"""Groq-hosted Whisper (open-weight model, hosted inference). Optional cloud backend.

Multipart POST to /audio/transcriptions with model, language, prompt and
response_format=verbose_json. verbose_json carries the decoded `duration`, so the 30 s limit
holds on this path too; a response without a usable duration is rejected (fail closed). The
upload's file name and MIME type follow the sniffed container. Error messages never include
the response body.
"""
from __future__ import annotations

from harness.providers.base import GROQ_BASE, ProviderResponseError
from harness.stt.base import STTProvider, check_audio, check_duration, clean_transcript


class GroqWhisperSTT(STTProvider):
    name = "stt.groq_whisper"

    def available(self) -> bool:
        return bool(self.env.get("GROQ_API_KEY")) and bool(self.env.get("GROQ_STT_MODEL"))

    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str:
        import httpx

        fmt = check_audio(audio)  # empty, tiny, oversized or unknown clips are never uploaded
        r = httpx.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.env['GROQ_API_KEY']}"},
            data={
                "model": self.env["GROQ_STT_MODEL"],
                "language": language,
                "prompt": initial_prompt,
                "response_format": "verbose_json",
            },
            files={"file": (fmt.filename, audio, fmt.mime_type)},
            timeout=60,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"groq stt status {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            raise ProviderResponseError("groq stt response is not JSON") from None
        if not isinstance(body, dict):
            raise ProviderResponseError("groq stt response is not a JSON object")
        check_duration(body.get("duration"))
        return clean_transcript(body.get("text"))
