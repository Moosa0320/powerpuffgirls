"""Groq-hosted open-weight vision model. Optional cloud backend."""
from __future__ import annotations

import base64
from typing import Any

from harness.jsonutil import parse_json_object
from harness.providers.base import GROQ_BASE, ProviderResponseError
from harness.vision.base import VISION_PROMPT, VisionProvider


class GroqVLM(VisionProvider):
    name = "vision.groq_vlm"

    def available(self) -> bool:
        return bool(self.env.get("GROQ_API_KEY")) and bool(self.env.get("GROQ_VISION_MODEL"))

    def _observe(self, image: bytes) -> dict[str, Any]:
        import httpx

        b64 = base64.b64encode(image).decode()
        r = httpx.post(
            f"{GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {self.env['GROQ_API_KEY']}"},
            json={
                "model": self.env["GROQ_VISION_MODEL"],
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]}],
            },
            timeout=60,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"groq vision status {r.status_code}")
        obj = parse_json_object(r.json()["choices"][0]["message"]["content"] or "")
        if obj is None:
            raise ProviderResponseError("vision model did not return JSON")
        return obj