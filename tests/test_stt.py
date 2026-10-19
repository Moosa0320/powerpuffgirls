"""STT backends: local faster-whisper and Groq Whisper (guide section 9, requirement 6).

No network and no model downloads: httpx.post is stubbed for Groq, and a fake `faster_whisper`
module replaces the real one (installed or not) in every test. The shared factory, timeouts,
availability and error-body leaks are covered in test_providers.py.
"""
from __future__ import annotations

import importlib.machinery
import io
import random
import sys
import threading
import time
import types
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from harness.providers.base import ProviderError
from harness.providers.factory import build_chain, call_with_fallback
from harness.stt.base import AGRI_PROMPT, MAX_AUDIO_BYTES, MIN_AUDIO_BYTES, sniff_container
from harness.stt.groq_whisper import GroqWhisperSTT
from harness.stt.local_whisper import LocalWhisperSTT

FAKE_KEY = "fake-key-fake-key-fake-key"  # must never appear in a ProviderError
GROQ_ENV = {"GROQ_API_KEY": FAKE_KEY, "GROQ_STT_MODEL": "whisper-large-v3-turbo"}
STT_ENV = {"STT_BACKEND": "groq", **GROQ_ENV, "WHISPER_MODEL_SIZE": "tiny"}
GUIDE_WORDS = ("urea", "DAP", "tomato", "pani", "spray")
URDU = "کل دو بوری یوریا ڈالی"

# Leading bytes of real recordings: (header, container it must be sniffed as).
HEADERS: dict[str, tuple[bytes, str]] = {
    "webm": (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x84webm", "webm"),  # Chrome, Edge
    "matroska": (b"\x1a\x45\xdf\xa3\xa3\x42\x86\x81\x01\x42\x82\x88matroska", "webm"),
    "ogg": (b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00", "ogg"),  # Firefox
    "mp4": (b"\x00\x00\x00\x1cftypiso5\x00\x00\x02\x00", "mp4"),  # Safari
    "m4a": (b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00", "mp4"),
    "wav": (b"RIFF\x24\x00\x00\x00WAVEfmt ", "wav"),
    "mp3-id3": (b"ID3\x04\x00\x00\x00\x00\x00\x00", "mp3"),
    "mp3-frame": (b"\xff\xfb\x90\x64\x00\x00", "mp3"),  # MPEG-1 layer III, 128 kbps, 44.1 kHz
    "flac": (b"fLaC\x00\x00\x00\x22", "flac"),
}
UPLOADS = {  # container -> (file name, MIME type) sent to Groq
    "webm": ("clip.webm", "audio/webm"), "ogg": ("clip.ogg", "audio/ogg"),
    "mp4": ("clip.m4a", "audio/mp4"), "wav": ("clip.wav", "audio/wav"),
    "mp3": ("clip.mp3", "audio/mpeg"), "flac": ("clip.flac", "audio/flac"),
}
NOT_AUDIO = {
    "aac-adts": b"\xff\xf1\x50\x80\x02\x1f\xfc",  # MPEG sync but layer 00: not MP3
    "jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF",
    "png": b"\x89PNG\r\n\x1a\n",
    "avi": b"RIFF\x24\x00\x00\x00AVI LIST",
    "text": b"kal do bori urea dali",
    "zeros": bytes(12),
}


def clip(kind: str = "webm", size: int = 4_000) -> bytes:
    """`size` bytes that start like a real recording of the given kind."""
    head = HEADERS[kind][0]
    return head + bytes(size - len(head))


def wav_clip(seconds: float, rate: int = 48_000) -> bytes:
    """A real 16-bit mono WAV file of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(2 * int(seconds * rate)))
    return buf.getvalue()


def verbose(text: str = URDU, duration: float | None = 4.2) -> httpx.Response:
    """A Groq verbose_json reply."""
    body: dict[str, Any] = {"task": "transcribe", "language": "Urdu", "text": text, "segments": []}
    if duration is not None:
        body["duration"] = duration
    return httpx.Response(200, json=body)


# --- fixtures: no network, fake faster-whisper ----------------------------------------------

@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def blocked(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        attempts.append(url)
        raise httpx.ConnectError("network disabled in unit tests")

    monkeypatch.setattr(httpx, "post", blocked)
    yield
    assert not attempts, "a unit test reached httpx.post without a stub"


class GroqStub:
    """Stands in for httpx.post: records each request and returns a scripted reply."""

    def __init__(self, reply: httpx.Response) -> None:
        self.reply = reply
        self.requests: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append({"url": url, **kwargs})
        return self.reply


@pytest.fixture()
def groq(monkeypatch: pytest.MonkeyPatch) -> Callable[[httpx.Response], GroqStub]:
    def install(reply: httpx.Response) -> GroqStub:
        stub = GroqStub(reply)
        monkeypatch.setattr(httpx, "post", stub)
        return stub

    return install


@dataclass
class FakeWhisper:
    """Script and call record for the fake faster_whisper module."""

    texts: list[str] = field(default_factory=lambda: [" kal do bori ", "", " urea dali "])
    duration: float | None = 12.5
    load_delay_s: float = 0.0
    loads: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    segments_decoded: int = 0


@pytest.fixture(autouse=True)
def whisper(monkeypatch: pytest.MonkeyPatch) -> FakeWhisper:
    """Replace faster_whisper with a fake and start every test with an empty model cache."""
    fake = FakeWhisper()

    class WhisperModel:
        def __init__(self, size: str, **kwargs: Any) -> None:
            time.sleep(fake.load_delay_s)
            fake.loads.append((size, kwargs))

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Iterator[Any], Any]:
            fake.calls.append({"audio": audio.read(), **kwargs})

            def segments() -> Iterator[Any]:  # lazy, like faster-whisper's generator
                for text in fake.texts:
                    fake.segments_decoded += 1
                    yield SimpleNamespace(text=text)

            return segments(), SimpleNamespace(duration=fake.duration)

    module = types.ModuleType("faster_whisper")
    module.__spec__ = importlib.machinery.ModuleSpec("faster_whisper", loader=None)
    module.WhisperModel = WhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    monkeypatch.setattr(LocalWhisperSTT, "_models", {})
    return fake


# --- Groq request shape (requirement 6.3) ------------------------------------------------------

def test_groq_request_sends_language_ur_the_agri_prompt_and_verbose_json(
    groq: Callable[[httpx.Response], GroqStub],
) -> None:
    stub = groq(verbose())
    stt = GroqWhisperSTT(env=GROQ_ENV)
    res = stt.transcribe(clip())
    assert res.ok, res.error
    assert res.value == URDU  # spoken Urdu comes back in Urdu script, unchanged
    [req] = stub.requests
    assert req["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert req["headers"] == {"Authorization": f"Bearer {FAKE_KEY}"}
    assert req["data"] == {"model": "whisper-large-v3-turbo", "language": "ur",
                           "prompt": AGRI_PROMPT, "response_format": "verbose_json"}
    assert 0 < req["timeout"] < stt.timeout_s


def test_agri_prompt_has_the_guide_words_and_fits_groq_prompt_limit() -> None:
    for word in GUIDE_WORDS:
        assert word in AGRI_PROMPT
    assert len(AGRI_PROMPT.encode("utf-8")) < 224  # a token is at least one byte: < 224 tokens


@pytest.mark.parametrize("kind", list(HEADERS), ids=list(HEADERS))
def test_groq_upload_is_named_and_typed_after_the_sniffed_container(
    groq: Callable[[httpx.Response], GroqStub], kind: str
) -> None:
    stub = groq(verbose())
    audio = clip(kind)
    assert GroqWhisperSTT(env=GROQ_ENV).transcribe(audio).ok
    filename, mime = UPLOADS[HEADERS[kind][1]]
    assert stub.requests[0]["files"] == {"file": (filename, audio, mime)}


# --- container sniffing --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", list(NOT_AUDIO), ids=list(NOT_AUDIO))
def test_sniffing_finds_no_container_in_other_data(kind: str) -> None:
    assert sniff_container(NOT_AUDIO[kind] + bytes(64)) is None


def test_sniffing_depends_only_on_the_leading_bytes() -> None:
    rng = random.Random(6)
    magic_first = {0x1A, ord("O"), ord("R"), ord("f"), ord("I"), 0xFF}
    other_first = [b for b in range(256) if b not in magic_first]
    for _ in range(300):
        head, container = HEADERS[rng.choice(sorted(HEADERS))]
        fmt = sniff_container(head + rng.randbytes(rng.randrange(64)))
        assert fmt is not None and fmt.container == container
        junk = bytes([rng.choice(other_first)]) + rng.randbytes(rng.randrange(64))
        assert sniff_container(junk) is None or junk[4:8] == b"ftyp"


# --- clip checks before any upload or model load (requirement 6.2) ---------------------------

BACKENDS: dict[str, Callable[[], GroqWhisperSTT | LocalWhisperSTT]] = {
    "groq": lambda: GroqWhisperSTT(env=GROQ_ENV),
    "local": lambda: LocalWhisperSTT(env={}),
}
BAD_CLIPS: dict[str, tuple[bytes, str]] = {
    "empty": (b"", "audio is empty"),
    "header-only": (clip("webm", 120), "audio is too short to transcribe"),
    "below-minimum": (clip("webm", MIN_AUDIO_BYTES - 1), "audio is too short to transcribe"),
    "over-byte-cap": (clip("webm", MAX_AUDIO_BYTES + 1), "audio is larger than 4,000,000 bytes"),
    "not-audio": (NOT_AUDIO["png"] + bytes(4_000), "unsupported audio format"),
}


@pytest.mark.parametrize("backend", list(BACKENDS), ids=list(BACKENDS))
@pytest.mark.parametrize(("audio", "message"), list(BAD_CLIPS.values()), ids=list(BAD_CLIPS))
def test_bad_clips_are_typed_errors_before_any_upload_or_model_load(
    whisper: FakeWhisper, backend: str, audio: bytes, message: str
) -> None:
    stt = BACKENDS[backend]()
    res = stt.transcribe(audio)
    assert res.error == ProviderError(stt.name, "bad_response", message)
    assert whisper.loads == []
    assert whisper.calls == []  # and the no_network guard shows Groq never posted


@pytest.mark.parametrize("size", [MIN_AUDIO_BYTES, MAX_AUDIO_BYTES], ids=["minimum", "byte-cap"])
def test_clip_size_bounds_are_inclusive_on_both_paths(
    groq: Callable[[httpx.Response], GroqStub], whisper: FakeWhisper, size: int
) -> None:
    stub = groq(verbose())
    audio = clip("webm", size)
    assert GroqWhisperSTT(env=GROQ_ENV).transcribe(audio).ok
    assert LocalWhisperSTT(env={}).transcribe(audio).ok
    assert len(stub.requests) == 1
    assert len(whisper.calls) == 1


def test_a_30_s_48_khz_wav_passes_the_byte_check_and_fits_vercel(
    groq: Callable[[httpx.Response], GroqStub],
) -> None:
    audio = wav_clip(30.0)
    assert 2_000_000 < len(audio) <= MAX_AUDIO_BYTES  # the old 2 MB cap rejected this clip
    assert MAX_AUDIO_BYTES + 100_000 <= 4_500_000  # room for multipart framing under 4.5 MB
    stub = groq(verbose(duration=30.0))
    assert GroqWhisperSTT(env=GROQ_ENV).transcribe(audio).ok
    assert stub.requests[0]["files"] == {"file": ("clip.wav", audio, "audio/wav")}


# --- the 30 s duration limit -----------------------------------------------------------------

@pytest.mark.parametrize(("duration", "ok"),
                         [(0.4, True), (30.0, True), (31.0, True), (31.01, False), (45.0, False)])
def test_groq_enforces_30_s_with_a_one_second_tolerance(
    groq: Callable[[httpx.Response], GroqStub], duration: float, ok: bool
) -> None:
    groq(verbose(duration=duration))
    res = GroqWhisperSTT(env=GROQ_ENV).transcribe(clip())
    assert res.ok is ok
    if not ok:
        assert res.error == ProviderError("stt.groq_whisper", "bad_response",
                                          "audio is longer than 30 s")


UNUSABLE_DURATIONS = {
    "missing": b'{"text": "kal pani diya"}',
    "null": b'{"text": "kal pani diya", "duration": null}',
    "string": b'{"text": "kal pani diya", "duration": "12.0"}',
    "bool": b'{"text": "kal pani diya", "duration": true}',
    "nan": b'{"text": "kal pani diya", "duration": NaN}',
    "negative": b'{"text": "kal pani diya", "duration": -1}',
}


@pytest.mark.parametrize("raw", list(UNUSABLE_DURATIONS.values()), ids=list(UNUSABLE_DURATIONS))
def test_groq_fails_closed_without_a_usable_duration(
    groq: Callable[[httpx.Response], GroqStub], raw: bytes
) -> None:
    groq(httpx.Response(200, content=raw))
    res = GroqWhisperSTT(env=GROQ_ENV).transcribe(clip())
    assert res.error == ProviderError("stt.groq_whisper", "bad_response", "audio duration unknown")


@pytest.mark.parametrize(("duration", "ok"), [(30.0, True), (31.0, True), (31.5, False),
                                              (None, False)])
def test_local_checks_the_duration_before_decoding_any_segment(
    whisper: FakeWhisper, duration: float | None, ok: bool
) -> None:
    whisper.duration = duration
    res = LocalWhisperSTT(env={}).transcribe(clip())
    assert res.ok is ok
    if not ok:
        assert res.error is not None
        assert res.error.kind == "bad_response"
        assert whisper.segments_decoded == 0


# --- Groq replies that must become typed errors without remote text -------------------------

GROQ_BAD_REPLIES: dict[str, tuple[Callable[[], httpx.Response], str]] = {
    "status": (lambda: httpx.Response(429, json={"error": {"message": f"slow down {FAKE_KEY}"}}),
               "groq stt status 429"),
    "not-json": (lambda: httpx.Response(200, text=f"<html>upstream {FAKE_KEY}</html>"),
                 "groq stt response is not JSON"),
    "not-an-object": (lambda: httpx.Response(200, json=[FAKE_KEY]),
                      "groq stt response is not a JSON object"),
    "text-not-a-string": (lambda: httpx.Response(200, json={"duration": 3.0,
                                                            "text": {"t": FAKE_KEY}}),
                          "transcript missing from response"),
    "blank-text": (lambda: verbose(text="  \n "), "no speech recognized"),
    "too-long": (lambda: verbose(text=f"leaked {FAKE_KEY}", duration=99.0),
                 "audio is longer than 30 s"),
}


@pytest.mark.parametrize(("reply", "message"), list(GROQ_BAD_REPLIES.values()),
                         ids=list(GROQ_BAD_REPLIES))
def test_groq_bad_replies_are_typed_errors_without_remote_text(
    groq: Callable[[httpx.Response], GroqStub], reply: Callable[[], httpx.Response], message: str
) -> None:
    groq(reply())
    res = GroqWhisperSTT(env=GROQ_ENV).transcribe(clip())
    assert res.error == ProviderError("stt.groq_whisper", "bad_response", message)
    assert FAKE_KEY not in repr(res)


# --- local faster-whisper path ---------------------------------------------------------------

@pytest.mark.parametrize(("texts", "expected"), [
    ([" kal do bori ", "", " urea dali "], "kal do bori urea dali"),
    ([" کل دو بوری", "  ", " یوریا ڈالی "], URDU),
], ids=["roman", "urdu-script"])
def test_local_passes_language_prompt_and_vad_filter_and_joins_segments(
    whisper: FakeWhisper, texts: list[str], expected: str
) -> None:
    whisper.texts = texts
    audio = clip("ogg")
    res = LocalWhisperSTT(env={}).transcribe(audio)
    assert res.ok, res.error
    assert res.value == expected
    assert whisper.calls == [{"audio": audio, "language": "ur", "initial_prompt": AGRI_PROMPT,
                              "vad_filter": True}]


@pytest.mark.parametrize("texts", [[], ["", "  "]], ids=["no-segments", "blank-segments"])
def test_local_silence_is_a_typed_error(whisper: FakeWhisper, texts: list[str]) -> None:
    whisper.texts = texts
    res = LocalWhisperSTT(env={}).transcribe(clip())
    assert res.error == ProviderError("stt.local_whisper", "bad_response", "no speech recognized")


def test_local_model_is_cached_per_size(whisper: FakeWhisper) -> None:
    tiny = LocalWhisperSTT(env={"WHISPER_MODEL_SIZE": "tiny"})._get_model()
    base = LocalWhisperSTT(env={"WHISPER_MODEL_SIZE": "base"})._get_model()
    assert base is not tiny  # changing the size never reuses the wrong model
    assert LocalWhisperSTT(env={"WHISPER_MODEL_SIZE": " tiny "})._get_model() is tiny
    assert whisper.loads == [("tiny", {"device": "cpu", "compute_type": "int8"}),
                             ("base", {"device": "cpu", "compute_type": "int8"})]


@pytest.mark.parametrize("env", [{}, {"WHISPER_MODEL_SIZE": "  "}], ids=["unset", "blank"])
def test_local_model_size_defaults_to_small(whisper: FakeWhisper, env: dict[str, str]) -> None:
    LocalWhisperSTT(env=env)._get_model()
    assert [size for size, _ in whisper.loads] == ["small"]


def test_concurrent_first_calls_load_the_model_once(whisper: FakeWhisper) -> None:
    whisper.load_delay_s = 0.05  # a slow load widens the race window
    stt = LocalWhisperSTT(env={"WHISPER_MODEL_SIZE": "tiny"})
    barrier = threading.Barrier(8)
    models: list[Any] = []

    def first_call() -> None:
        barrier.wait()
        models.append(stt._get_model())

    threads = [threading.Thread(target=first_call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(models) == 8
    assert len(whisper.loads) == 1
    assert all(m is models[0] for m in models)


def test_missing_faster_whisper_is_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # not importable
    stt = LocalWhisperSTT(env={})
    assert stt.available() is False
    res = stt.transcribe(clip())  # called anyway, as with a broken install
    assert res.error == ProviderError("stt.local_whisper", "unavailable", "ModuleNotFoundError")


# --- fallback chain: Groq, then local, then typed input (requirement 6.4) --------------------

def test_chain_falls_back_from_groq_to_local(
    groq: Callable[[httpx.Response], GroqStub], whisper: FakeWhisper
) -> None:
    stub = groq(httpx.Response(503, text="over capacity"))
    chain = build_chain("stt", env=STT_ENV)
    assert [type(p) for p in chain] == [GroqWhisperSTT, LocalWhisperSTT]
    res = call_with_fallback(chain, "transcribe", clip())
    assert res.ok, res.error
    assert res.value == "kal do bori urea dali"
    assert len(stub.requests) == 1
    assert [size for size, _ in whisper.loads] == ["tiny"]


Setup = Callable[[pytest.MonkeyPatch, Callable[[httpx.Response], GroqStub], FakeWhisper], bytes]


def _too_long(mp: pytest.MonkeyPatch, groq: Callable[..., GroqStub], fw: FakeWhisper) -> bytes:
    groq(verbose(duration=45.0))
    fw.duration = 45.0
    return clip()


def _empty(mp: pytest.MonkeyPatch, groq: Callable[..., GroqStub], fw: FakeWhisper) -> bytes:
    return b""  # no Groq stub: the no_network guard fails the test if Groq posts


def _bad_reply_broken_local(
    mp: pytest.MonkeyPatch, groq: Callable[..., GroqStub], fw: FakeWhisper
) -> bytes:
    groq(httpx.Response(200, text=f"<html>{FAKE_KEY}</html>"))
    mp.setitem(sys.modules, "faster_whisper", None)
    mp.setattr(LocalWhisperSTT, "available", lambda self: True)  # installed but broken
    return clip()


def _no_faster_whisper(
    mp: pytest.MonkeyPatch, groq: Callable[..., GroqStub], fw: FakeWhisper
) -> bytes:
    groq(httpx.Response(500, text=f"internal error {FAKE_KEY}"))
    mp.setitem(sys.modules, "faster_whisper", None)  # local drops out of the chain
    return clip()


CHAIN_FAILURES: dict[str, tuple[Setup, str]] = {
    "too-long": (_too_long, "stt.groq_whisper:bad_response; stt.local_whisper:bad_response"),
    "empty-audio": (_empty, "stt.groq_whisper:bad_response; stt.local_whisper:bad_response"),
    "bad-reply-broken-local": (_bad_reply_broken_local,
                               "stt.groq_whisper:bad_response; stt.local_whisper:unavailable"),
    "no-faster-whisper": (_no_faster_whisper, "stt.groq_whisper:bad_response"),
}


@pytest.mark.parametrize(("setup", "tried"), list(CHAIN_FAILURES.values()),
                         ids=list(CHAIN_FAILURES))
def test_every_stt_failure_ends_in_a_typed_input_error(
    monkeypatch: pytest.MonkeyPatch, groq: Callable[[httpx.Response], GroqStub],
    whisper: FakeWhisper, setup: Setup, tried: str,
) -> None:
    audio = setup(monkeypatch, groq, whisper)
    res = call_with_fallback(build_chain("stt", env=STT_ENV), "transcribe", audio)
    assert res.value is None
    assert res.error is not None
    assert (res.error.provider, res.error.kind) == ("chain", "unavailable")
    assert res.error.message.startswith(tried + " ")
    assert "typed input" in res.error.message
    assert FAKE_KEY not in repr(res)
