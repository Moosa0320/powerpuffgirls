"""Tolerant extraction of a JSON object from model text."""
from __future__ import annotations

import json
from typing import Any


def extract_json_text(text: str) -> str:
    """Return the substring from the first '{' to the last '}'. Raises ValueError if absent."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(extract_json_text(text))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None