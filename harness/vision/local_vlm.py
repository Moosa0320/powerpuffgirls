"""Local open-weight VLM via Ollama."""
from __future__ import annotations

import base64
from typing import Any

from harness.jsonutil import parse_json_object
from harness.providers.base import ProviderResponseError
from harness.vision.base import VISION_PROMPT, VisionProvider


class LocalVLM(VisionProvider):
    name = "vision.local_vlm"

    def _observe(self, image: bytes) -> dict[str, Any]:
        import httpx

        base = self.env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        r = httpx.post(
            f"{base}/api/chat",
            json={
                "model": self.env.get("OLLAMA_VISION_MODEL", "llava"),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [{"role": "user", "content": VISION_PROMPT,
                              "images": [base64.b64encode(image).decode()]}],
            },
            timeout=120,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"ollama vision status {r.status_code}")
        obj = parse_json_object((r.json().get("message") or {}).get("content", ""))
        if obj is None:
            raise ProviderResponseError("vision model did not return JSON")
        return obj