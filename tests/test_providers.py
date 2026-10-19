"""Provider interfaces, env-driven factory and fallback chain (guide 7.1, requirement 4).

No network: tests use the fakes, or a stubbed httpx.post for the real backends. An autouse
guard fails any test whose code reaches httpx.post without a stub.
"""
from __future__ import annotations

import inspect
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from harness.llm.base import LLMProvider
from harness.llm.groq import GroqLLM
from harness.llm.ollama import OllamaLLM
from harness.providers.base import Provider, ProviderError, safe_call
from harness.providers.factory import (
    ENV_KEYS,
    REGISTRY,
    _resolve,
    build_chain,
    call_with_fallback,
    first_provider,
)
from harness.providers.fakes import FakeLLM, FakeSTT, FakeTTS, FakeVision
from harness.stt.base import STTProvider
from harness.stt.groq_whisper import GroqWhisperSTT
from harness.stt.local_whisper import LocalWhisperSTT
from harness.tts.base import TTSProvider
from harness.tts.elevenlabs import ElevenLabsTTS
from harness.tts.piper_local import PiperTTS
from harness.vision.base import OBSERVATION_KEYS, VisionProvider
from harness.vision.groq_vlm import GroqVLM
from harness.vision.hf_vlm import HfVLM
from harness.vision.local_vlm import LocalVLM

ROOT = Path(__file__).resolve().parents[1]
FAMILIES: dict[str, type[Provider]] = {
    "stt": STTProvider, "llm": LLMProvider, "vision": VisionProvider, "tts": TTSProvider,
}
MESSAGES = [{"role": "user", "content": "kal 2 bori urea dali"}]
SECRET = "sk-test-0123456789abcdef"  # fake key; it must never appear in a ProviderError
GROQ_ENV = {"GROQ_API_KEY": SECRET, "GROQ_STT_MODEL": "stt-model",
            "GROQ_LLM_MODEL": "llm-model", "GROQ_VISION_MODEL": "vision-model"}
ELEVEN_ENV = {"ELEVENLABS_API_KEY": SECRET, "ELEVENLABS_VOICE_ID": "voice-1"}
# Any existing executable stands in for the Piper binary: only availability is checked.
PIPER_ENV = {"PIPER_BIN": sys.executable, "PIPER_VOICE": "ur_PK-voice.onnx"}
# WebM magic bytes padded past the STT minimum clip size, so real STT backends accept it.
WEBM_CLIP = b"\x1a\x45\xdf\xa3" + bytes(2_000)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def blocked(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        attempts.append(url)
        raise httpx.ConnectError("network disabled in unit tests")

    monkeypatch.setattr(httpx, "post", blocked)
    yield
    assert not attempts, "a unit test reached httpx.post without a stub"


@pytest.fixture()
def whisper_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Count local faster-whisper as installed, whatever this machine has."""
    monkeypatch.setattr(LocalWhisperSTT, "available", lambda self: True)


def _types(chain: list[Provider]) -> list[type[Provider]]:
    return [type(p) for p in chain]


# --- safe_call: timeouts and typed errors -------------------------------------------------

def test_safe_call_success() -> None:
    res = safe_call("test", lambda x: x * 2, 21)
    assert res.ok
    assert res.value == 42
    assert res.error is None


def test_safe_call_timeout_is_a_typed_timeout() -> None:
    release = threading.Event()

    def slow() -> str:
        release.wait(5)
        return "done"

    try:
        res = safe_call("slow_test", slow, timeout=0.05)
    finally:
        release.set()  # free the worker thread
    assert not res.ok
    assert res.value is None
    assert res.error is not None
    assert res.error.provider == "slow_test"
    assert res.error.kind == "timeout"


@pytest.mark.parametrize(
    ("exc", "leaked"),
    [
        (httpx.ReadTimeout(f"read timed out: https://api.groq.com/openai/v1?key={SECRET}"), SECRET),
        (subprocess.TimeoutExpired(["piper", "--model", "C:/farm/ur_voice.onnx"], 60),
         "ur_voice.onnx"),
        (TimeoutError(f"socket timed out after sending {SECRET}"), SECRET),
    ],
    ids=["httpx", "subprocess", "builtin"],
)
def test_timeouts_raised_inside_a_backend_are_typed_timeouts(exc: Exception, leaked: str) -> None:
    def raiser() -> None:
        raise exc

    res = safe_call("backend", raiser)
    assert res.error is not None
    assert res.error.kind == "timeout"
    assert leaked not in repr(res.error)


@pytest.mark.parametrize(
    "exc",
    [
        ValueError(f"bad api key {SECRET}"),
        httpx.ConnectError(f"cannot reach https://router.huggingface.co/v1 with Bearer {SECRET}"),
        OSError("No such file: C:/farm/audio/clip-17.webm"),
    ],
    ids=["value", "connect", "os"],
)
def test_raw_exception_messages_never_leak_into_provider_error(exc: Exception) -> None:
    def raiser() -> None:
        raise exc

    res = safe_call("backend", raiser)
    assert res.error == ProviderError("backend", "unavailable", type(exc).__name__)
    assert str(exc) not in repr(res.error)


# --- interfaces and registry ----------------------------------------------------------------

@pytest.mark.parametrize("base", list(FAMILIES.values()), ids=list(FAMILIES))
def test_every_family_base_class_is_abstract(base: type[Provider]) -> None:
    assert inspect.isabstract(base)
    with pytest.raises(TypeError):
        base(env={})


REGISTERED = [(kind, name) for kind, backends in REGISTRY.items()
              for name, target in backends.items() if target is not None]


@pytest.mark.parametrize(("kind", "name"), REGISTERED, ids=[f"{k}-{n}" for k, n in REGISTERED])
def test_registry_entries_resolve_to_concrete_family_backends(kind: str, name: str) -> None:
    cls = _resolve(REGISTRY[kind][name])
    assert issubclass(cls, FAMILIES[kind])
    assert not inspect.isabstract(cls)


# --- fakes ------------------------------------------------------------------------------------

def test_fake_llm_replies() -> None:
    fake = FakeLLM(replies=['{"hello": "world"}'])
    res = fake.chat(MESSAGES)
    assert res.ok
    assert res.value is not None
    assert res.value.content == '{"hello": "world"}'


def test_fake_stt_transcribe() -> None:
    res = FakeSTT(text="aaj pani diya").transcribe(b"fake_wav")
    assert res.ok
    assert res.value == "aaj pani diya"

    res_fail = FakeSTT(fail=True).transcribe(b"fake_wav")
    assert not res_fail.ok
    assert res_fail.error is not None
    assert res_fail.error.kind == "bad_response"


def test_fake_vision_keeps_only_schema_keys_and_fake_tts_returns_audio() -> None:
    vision = FakeVision(observation={"leaf_color": "yellow", "spots": True, "disease": "blight"})
    vres = vision.observe(b"fake_jpg")
    assert vres.ok
    assert vres.value is not None
    assert set(vres.value) == set(OBSERVATION_KEYS)  # "disease" dropped, missing keys are None
    assert vres.value["leaf_color"] == "yellow"
    assert vres.value["spots"] is True
    assert vres.value["wilting"] is None

    tres = FakeTTS(env={}).speak("hello")
    assert tres.ok
    assert tres.value == b"hello"


# --- env selection ----------------------------------------------------------------------------

SELECTION: dict[str, tuple[str, dict[str, str], list[type[Provider]]]] = {
    "stt-default": ("stt", {}, [LocalWhisperSTT]),
    "stt-groq": ("stt", {"STT_BACKEND": "groq", **GROQ_ENV}, [GroqWhisperSTT, LocalWhisperSTT]),
    "llm-default": ("llm", {}, [OllamaLLM]),
    "llm-groq": ("llm", {"LLM_BACKEND": " Groq ", **GROQ_ENV}, [GroqLLM, OllamaLLM]),
    "vision-default": ("vision", {}, [LocalVLM]),
    "vision-groq": ("vision", {"VISION_BACKEND": "groq", **GROQ_ENV}, [GroqVLM, LocalVLM]),
    "vision-hf": ("vision", {"VISION_BACKEND": "hf", "HF_TOKEN": SECRET}, [HfVLM, LocalVLM]),
    "tts-default": ("tts", dict(PIPER_ENV), [PiperTTS]),
    "tts-elevenlabs": ("tts", {"TTS_BACKEND": "elevenlabs", **ELEVEN_ENV, **PIPER_ENV},
                       [ElevenLabsTTS, PiperTTS]),
    "tts-none": ("tts", {"TTS_BACKEND": "none", **ELEVEN_ENV, **PIPER_ENV}, []),
}


@pytest.mark.usefixtures("whisper_installed")
@pytest.mark.parametrize(("kind", "env", "expected"), list(SELECTION.values()), ids=list(SELECTION))
def test_env_selects_the_backend_for_each_kind(
    kind: str, env: dict[str, str], expected: list[type[Provider]]
) -> None:
    chain = build_chain(kind, env=env)
    assert _types(chain) == expected
    assert all(p.env is env for p in chain)  # backends read the given env, not os.environ


def test_first_provider_is_the_head_of_the_chain() -> None:
    vision = first_provider("vision", env={"VISION_BACKEND": "hf", "HF_TOKEN": SECRET})
    assert isinstance(vision, HfVLM)
    assert first_provider("tts", env={"TTS_BACKEND": "none"}) is None


def test_unknown_provider_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_chain("ocr", env={})


# --- fallback chain ---------------------------------------------------------------------------

FALLBACK: dict[str, tuple[str, dict[str, str], list[type[Provider]]]] = {
    "stt-groq-no-key": ("stt", {"STT_BACKEND": "groq", "GROQ_STT_MODEL": "stt-model"},
                        [LocalWhisperSTT]),
    "llm-groq-no-model": ("llm", {"LLM_BACKEND": "groq", "GROQ_API_KEY": SECRET}, [OllamaLLM]),
    "vision-groq-no-key": ("vision", {"VISION_BACKEND": "groq"}, [LocalVLM]),
    "vision-hf-blank-token": ("vision", {"VISION_BACKEND": "hf", "HF_TOKEN": ""}, [LocalVLM]),
    "tts-elevenlabs-no-voice": ("tts", {"TTS_BACKEND": "elevenlabs",
                                        "ELEVENLABS_API_KEY": SECRET, **PIPER_ENV}, [PiperTTS]),
    "tts-elevenlabs-no-piper": ("tts", {"TTS_BACKEND": "elevenlabs", **ELEVEN_ENV,
                                        "ELEVENLABS_VOICE_ID": ""}, []),
    "llm-unknown-name": ("llm", {"LLM_BACKEND": "not-a-backend"}, [OllamaLLM]),
}


@pytest.mark.usefixtures("whisper_installed")
@pytest.mark.parametrize(("kind", "env", "expected"), list(FALLBACK.values()), ids=list(FALLBACK))
def test_unavailable_cloud_backend_falls_back_to_local(
    kind: str, env: dict[str, str], expected: list[type[Provider]]
) -> None:
    assert _types(build_chain(kind, env=env)) == expected


def test_no_stt_backend_means_typed_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LocalWhisperSTT, "available", lambda self: False)
    chain = build_chain("stt", env={"STT_BACKEND": "groq"})
    assert chain == []
    res = call_with_fallback(chain, "transcribe", b"audio")
    assert res.error is not None
    assert res.error.kind == "not_configured"
    assert "typed input" in res.error.message


def test_runtime_fallback_uses_the_local_backend_when_cloud_fails() -> None:
    cloud = FakeLLM(replies=[httpx.ConnectError("cloud down")])
    local = FakeLLM(replies=["local reply"])
    res = call_with_fallback([cloud, local], "chat", MESSAGES)
    assert res.ok
    assert res.value is not None
    assert res.value.content == "local reply"
    assert len(cloud.calls) == 1
    assert len(local.calls) == 1


def test_factory_passes_env_to_registered_backends() -> None:
    env = {"LLM_BACKEND": "custom"}
    chain = build_chain("llm", env=env, registry={"llm": {"custom": FakeLLM, "ollama": FakeLLM}})
    assert len(chain) == 2
    for provider in chain:
        assert isinstance(provider, FakeLLM)
        assert provider.env is env
        assert provider.replies == []


class _BrokenInit(FakeLLM):
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        raise RuntimeError("cannot start")


class _BrokenCheck(FakeLLM):
    def available(self) -> bool:
        raise RuntimeError("check failed")


@pytest.mark.parametrize(
    "broken", ["harness.llm.no_such_backend:Missing", _BrokenInit, _BrokenCheck],
    ids=["import", "init", "available"],
)
def test_a_broken_backend_never_breaks_the_chain(broken: Any) -> None:
    registry = {"llm": {"cloud": broken, "ollama": FakeLLM}}
    chain = build_chain("llm", env={"LLM_BACKEND": "cloud"}, registry=registry)
    assert _types(chain) == [FakeLLM]


def test_empty_chain_returns_a_typed_not_configured_error() -> None:
    res = call_with_fallback([], "speak", "salam")
    assert not res.ok
    assert res.value is None
    assert res.error is not None
    assert (res.error.provider, res.error.kind) == ("chain", "not_configured")
    assert "no audio" in res.error.message


def test_all_failing_chain_returns_a_typed_error_without_raw_messages() -> None:
    cloud = FakeLLM(replies=[httpx.ConnectError(f"https://api.groq.com/openai/v1 Bearer {SECRET}")])
    local = FakeLLM(replies=[])  # nothing scripted -> bad_response
    res = call_with_fallback([cloud, local], "chat", MESSAGES)
    assert not res.ok
    assert res.error is not None
    assert (res.error.provider, res.error.kind) == ("chain", "unavailable")
    assert "llm.fake:unavailable" in res.error.message
    assert "llm.fake:bad_response" in res.error.message
    assert "typed input" in res.error.message
    assert SECRET not in res.error.message
    assert "api.groq.com" not in res.error.message


# --- every family call has a timeout -------------------------------------------------------------

def _block(provider: Provider, impl: str, release: threading.Event) -> Provider:
    """Make `impl` wait for `release`, so the call outlives a tiny provider timeout."""
    original = getattr(provider, impl)

    def wait_then_run(*args: Any) -> Any:
        release.wait(5)
        return original(*args)

    setattr(provider, impl, wait_then_run)
    provider.timeout_s = 0.05
    return provider


FAMILY_CALLS: dict[str, tuple[Callable[[], Provider], str, str, tuple[Any, ...]]] = {
    "stt": (lambda: FakeSTT(text="late"), "_transcribe", "transcribe", (b"audio",)),
    "llm": (lambda: FakeLLM(replies=["late"]), "_chat", "chat", (MESSAGES,)),
    "vision": (lambda: FakeVision(), "_observe", "observe", (b"jpg",)),
    "tts": (lambda: FakeTTS(env={}), "_speak", "speak", ("salam",)),
}


@pytest.mark.parametrize(("make", "impl", "method", "args"), list(FAMILY_CALLS.values()),
                         ids=list(FAMILY_CALLS))
def test_every_family_call_is_capped_by_the_provider_timeout(
    make: Callable[[], Provider], impl: str, method: str, args: tuple[Any, ...]
) -> None:
    release = threading.Event()
    provider = _block(make(), impl, release)
    try:
        res = getattr(provider, method)(*args)
    finally:
        release.set()
    assert res.error is not None
    assert res.error.kind == "timeout"
    assert res.error.provider == provider.name


# --- real backends: errors stay typed and never echo remote text ---------------------------------

BACKEND_CALLS: dict[str, tuple[Callable[[], Provider], str, tuple[Any, ...]]] = {
    "groq-stt": (lambda: GroqWhisperSTT(env=GROQ_ENV), "transcribe", (WEBM_CLIP,)),
    "groq-llm": (lambda: GroqLLM(env=GROQ_ENV), "chat", (MESSAGES,)),
    "groq-vision": (lambda: GroqVLM(env=GROQ_ENV), "observe", (b"jpg",)),
    "hf-vision": (lambda: HfVLM(env={"HF_TOKEN": SECRET}), "observe", (b"jpg",)),
    "elevenlabs": (lambda: ElevenLabsTTS(env=ELEVEN_ENV), "speak", ("salam",)),
    "ollama-llm": (lambda: OllamaLLM(env={}), "chat", (MESSAGES,)),
    "ollama-vision": (lambda: LocalVLM(env={}), "observe", (b"jpg",)),
}


@pytest.mark.parametrize(("make", "method", "args"), list(BACKEND_CALLS.values()),
                         ids=list(BACKEND_CALLS))
def test_backend_error_response_body_never_leaks(
    monkeypatch: pytest.MonkeyPatch, make: Callable[[], Provider], method: str,
    args: tuple[Any, ...],
) -> None:
    body = f'{{"error": "invalid key {SECRET}", "see": "https://router.huggingface.co/docs"}}'
    sent: list[str] = []

    def reject(url: str, *a: Any, **kw: Any) -> httpx.Response:
        sent.append(url)
        return httpx.Response(401, text=body)

    monkeypatch.setattr(httpx, "post", reject)
    res = getattr(make(), method)(*args)
    assert len(sent) == 1  # the stub answered, not the network
    assert res.error is not None
    assert res.error.kind == "bad_response"
    assert "401" in res.error.message
    assert SECRET not in res.error.message
    assert "huggingface.co" not in res.error.message


# --- availability -------------------------------------------------------------------------------

CLOUD_ENV: dict[type[Provider], dict[str, str]] = {
    GroqWhisperSTT: {"GROQ_API_KEY": SECRET, "GROQ_STT_MODEL": "stt-model"},
    GroqLLM: {"GROQ_API_KEY": SECRET, "GROQ_LLM_MODEL": "llm-model"},
    GroqVLM: {"GROQ_API_KEY": SECRET, "GROQ_VISION_MODEL": "vision-model"},
    HfVLM: {"HF_TOKEN": SECRET},
    ElevenLabsTTS: ELEVEN_ENV,
}


@pytest.mark.parametrize(("cls", "required"), list(CLOUD_ENV.items()),
                         ids=[c.__name__ for c in CLOUD_ENV])
def test_cloud_backend_is_unavailable_without_its_env_vars(
    cls: type[Provider], required: dict[str, str]
) -> None:
    assert cls(env={}).available() is False
    for key in required:
        assert cls(env={k: v for k, v in required.items() if k != key}).available() is False
        assert cls(env={**required, key: ""}).available() is False
    assert cls(env=required).available() is True


def test_piper_needs_a_binary_and_a_voice(tmp_path: Path) -> None:
    assert PiperTTS(env={"PIPER_BIN": sys.executable}).available() is False
    assert PiperTTS(env={**PIPER_ENV, "PIPER_BIN": str(tmp_path / "no-piper")}).available() is False
    assert PiperTTS(env=PIPER_ENV).available() is True


# --- .env.example documents every provider variable -----------------------------------------

ENV_READ = re.compile(r"""env(?:\.get\(|\[)\s*["']([A-Z][A-Z0-9_]*)["']""")
SECRET_VARS = ("GROQ_API_KEY", "HF_TOKEN", "ELEVENLABS_API_KEY", "APP_PASSCODE")


def _provider_env_vars() -> set[str]:
    names = set(ENV_KEYS.values())
    for package in ("providers", "stt", "llm", "vision", "tts"):
        for path in (ROOT / "harness" / package).glob("*.py"):
            names.update(ENV_READ.findall(path.read_text(encoding="utf-8")))
    return names


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def test_env_example_lists_every_provider_variable_without_secret_values() -> None:
    read = _provider_env_vars()
    assert {"HF_TOKEN", "HF_VISION_MODEL", "ELEVENLABS_VOICE_ID", "PIPER_VOICE"} <= read
    example = _env_example()
    assert sorted(read - example.keys()) == []
    for name in SECRET_VARS:
        assert example[name] == "", f"{name} must be blank in .env.example"
