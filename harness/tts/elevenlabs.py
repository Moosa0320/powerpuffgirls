"""ElevenLabs TTS. Optional proprietary service, cloud report playback only."""
from __future__ import annotations

from harness.providers.base import ProviderResponseError
from harness.tts.base import TTSProvider


class ElevenLabsTTS(TTSProvider):
    name = "tts.elevenlabs"

    def available(self) -> bool:
        return bool(self.env.get("ELEVENLABS_API_KEY")) and bool(self.env.get("ELEVENLABS_VOICE_ID"))

    def _speak(self, text: str, lang: str) -> bytes:
        import httpx

        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.env['ELEVENLABS_VOICE_ID']}",
            headers={"xi-api-key": self.env["ELEVENLABS_API_KEY"], "accept": "audio/mpeg"},
            json={"text": text, "model_id": self.env.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")},
            timeout=60,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"elevenlabs status {r.status_code}")
        return r.content