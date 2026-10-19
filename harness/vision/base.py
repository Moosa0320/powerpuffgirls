"""Vision interface. Returns visible symptoms only, never a diagnosis (guide section 9)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from harness.providers.base import Provider, Result, safe_call

OBSERVATION_KEYS = ("leaf_color", "pattern", "spots", "wilting", "affected_area", "notes")
VISION_PROMPT = (
    "Describe only what is visible on the plant in this photo. Do not name any disease, "
    "cause, pest or treatment. Return JSON with keys: leaf_color, pattern, spots, wilting, "
    "affected_area, notes. Use null for anything you cannot see."
)


class VisionProvider(Provider, ABC):
    name = "vision"

    @abstractmethod
    def _observe(self, image: bytes) -> dict[str, Any]: ...

    def _observe_checked(self, image: bytes) -> dict[str, Any]:
        raw = self._observe(image)
        return {k: raw.get(k) for k in OBSERVATION_KEYS}  # drop anything outside the schema

    def observe(self, image: bytes) -> Result[dict[str, Any]]:
        return safe_call(self.name, self._observe_checked, image, timeout=self.timeout_s)