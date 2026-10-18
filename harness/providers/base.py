"""Shared provider types: typed errors, Result wrapper and safe_call with timeout (guide 7.1).

Every backend call goes through safe_call, so callers only ever see a Result,
never a raw exception.
"""
from __future__ import annotations

import concurrent.futures
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

DEFAULT_TIMEOUT_S = 90.0
GROQ_BASE = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class ProviderError:
    provider: str
    kind: str  # timeout | unavailable | bad_response | not_configured
    message: str


@dataclass(frozen=True)
class Result(Generic[T]):
    value: T | None = None
    error: ProviderError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ProviderResponseError(Exception):
    """Raised inside a backend when the remote response is unusable."""


_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def safe_call(
    provider: str, fn: Callable[..., T], *args: Any, timeout: float = DEFAULT_TIMEOUT_S, **kwargs: Any
) -> Result[T]:
    future = _POOL.submit(fn, *args, **kwargs)
    try:
        return Result(value=future.result(timeout=timeout))
    except concurrent.futures.TimeoutError:
        return Result(error=ProviderError(provider, "timeout", f"no response within {timeout}s"))
    except ProviderResponseError as exc:
        return Result(error=ProviderError(provider, "bad_response", str(exc)[:200]))
    except Exception as exc:  # noqa: BLE001 - never leak raw exceptions
        # Only the exception type is reported: messages can contain URLs, paths or keys.
        return Result(error=ProviderError(provider, "unavailable", type(exc).__name__))


class Provider:
    """Common base for every backend: a name, an env mapping and an availability check."""

    name: str = "provider"

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self.env: Mapping[str, str] = os.environ if env is None else env

    def available(self) -> bool:
        return True