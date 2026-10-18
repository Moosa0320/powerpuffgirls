"""HuggingFace Router hosted open-weight VLM (Qwen-VL). Optional cloud backend."""
from __future__ import annotations

import base64
from typing import Any

from harness.jsonutil import parse_json_object
from harness.providers.base import ProviderResponseError
from harness.vision.base import VISION_PROMPT, VisionProvider

HF_ROUTER_BASE = "https://router.huggingface.co/v1"


class HfVLM(VisionProvider):
    name = "vision.hf_vlm"

    def available(self) -> bool:
        return bool(self.env.get("HF_TOKEN"))

    def _observe(self, image: bytes) -> dict[str, Any]:
        import httpx

        b64 = base64.b64encode(image).decode()
        token = self.env.get("HF_TOKEN", "")
        model = self.env.get("HF_VISION_MODEL", "Qwen/Qwen3-VL-2B-Instruct:featherless-ai")
        r = httpx.post(
            f"{HF_ROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT + "\nReturn ONLY valid JSON."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
            },
            timeout=90,
        )
        if r.status_code != 200:
            raise ProviderResponseError(f"hf router vision status {r.status_code}: {r.text[:200]}")
        content = r.json()["choices"][0]["message"]["content"] or ""
        obj = parse_json_object(content)
        if obj is None:
            raise ProviderResponseError("hf vision model did not return JSON")
        return obj
