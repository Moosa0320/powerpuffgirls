"""Local open-weight TTS via the Piper CLI."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from harness.tts.base import TTSProvider


class PiperTTS(TTSProvider):
    name = "tts.piper"

    def _bin(self) -> str:
        return self.env.get("PIPER_BIN", "piper")

    def available(self) -> bool:
        return shutil.which(self._bin()) is not None and bool(self.env.get("PIPER_VOICE"))

    def _speak(self, text: str, lang: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "speech.wav")
            subprocess.run(
                [self._bin(), "--model", self.env["PIPER_VOICE"], "--output_file", out],
                input=text.encode("utf-8"), check=True, timeout=60, capture_output=True,
            )
            with open(out, "rb") as fh:
                return fh.read()