"""Env-driven provider selection with an automatic fallback chain (guide 7.1).

Chain order: configured backend -> local backend (if available) -> nothing.
An empty or exhausted chain returns a typed error; callers then fall back to
typed input (STT) or no audio (TTS).
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from typing import Any

from harness.providers.base import Provider, ProviderError, Result

ENV_KEYS = {"stt": "STT_BACKEND", "llm": "LLM_BACKEND", "vision": "VISION_BACKEND", "tts": "TTS_BACKEND"}
LOCAL_DEFAULTS = {"stt": "local", "llm": "ollama", "vision": "local", "tts": "piper"}
REGISTRY: dict[str, dict[str, Any]] = {
    "stt": {"local": "harness.stt.local_whisper:LocalWhisperSTT",
            "groq": "harness.stt.groq_whisper:GroqWhisperSTT"},
    "llm": {"ollama": "harness.llm.ollama:OllamaLLM", "groq": "harness.llm.groq:GroqLLM"},
    "vision": {"local": "harness.vision.local_vlm:LocalVLM", "groq": "harness.vision.groq_vlm:GroqVLM"},
    "tts": {"piper": "harness.tts.piper_local:PiperTTS",
            "elevenlabs": "harness.tts.elevenlabs:ElevenLabsTTS", "none": None},
}


def _resolve(target: Any) -> Any:
    if not isinstance(target, str):
        return target
    module, cls = target.split(":")
    return getattr(importlib.import_module(module), cls)


def build_chain(
    kind: str, env: Mapping[str, str] | None = None, registry: dict[str, dict[str, Any]] | None = None
) -> list[Provider]:
    if kind not in ENV_KEYS:
        raise ValueError(f"unknown provider kind: {kind}")
    env = os.environ if env is None else env
    registry = REGISTRY if registry is None else registry
    configured = (env.get(ENV_KEYS[kind]) or LOCAL_DEFAULTS[kind]).strip().lower()
    names = [configured]
    if configured != "none" and LOCAL_DEFAULTS[kind] not in names:
        names.append(LOCAL_DEFAULTS[kind])
    chain: list[Provider] = []
    for name in names:
        cls = _resolve(registry.get(kind, {}).get(name))
        if cls is None:
            continue
        try:
            provider = cls(env)
            if provider.available():
                chain.append(provider)
        except Exception:  # noqa: BLE001 - a broken backend must never break the chain
            continue
    return chain


def first_provider(kind: str, env: Mapping[str, str] | None = None) -> Provider | None:
    chain = build_chain(kind, env)
    return chain[0] if chain else None


def call_with_fallback(chain: list[Provider], method: str, *args: Any, **kwargs: Any) -> Result[Any]:
    errors: list[str] = []
    for provider in chain:
        result = getattr(provider, method)(*args, **kwargs)
        if result.ok:
            return result
        errors.append(f"{result.error.provider}:{result.error.kind}")
    if not errors:
        return Result(error=ProviderError("chain", "not_configured",
                                          "no backend available; use typed input / no audio"))
    return Result(error=ProviderError("chain", "unavailable",
                                      "; ".join(errors) + " (use typed input / no audio)"))