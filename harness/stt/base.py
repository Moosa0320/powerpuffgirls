"""Speech-to-text interface and the clip checks every backend runs (guide section 9, req 6).

Clip limits:
- MAX_AUDIO_SECONDS is the real limit (requirement 6.2). Each backend checks the duration it
  measured after decoding (faster-whisper `info.duration`, Groq verbose_json `duration`) and
  rejects clips over MAX_AUDIO_SECONDS + DURATION_TOLERANCE_S. The tolerance absorbs the
  browser's stop latency and codec padding.
- MAX_AUDIO_BYTES is only a cheap pre-check before any upload or decode. Vercel caps a function's
  request body at 4.5 MB, so 4 MB leaves room for multipart framing. It still admits a 30 s
  48 kHz 16-bit mono WAV (about 2.9 MB); 30 s of Opus or AAC from MediaRecorder is far smaller.
- MIN_AUDIO_BYTES rejects empty and header-only clips before any network call or model load.

Silence: the local backend runs faster-whisper's VAD filter; the browser auto-stops on silence
(task 12), so Groq receives the clip as recorded.

The container is sniffed from magic bytes, never taken from the client. Unknown formats are a
typed error, not a guess. The recognised set (WebM/Matroska, Ogg, MP4/M4A, WAV, MP3, FLAC) covers
Chrome/Edge, Firefox and Safari recordings and every upload type Groq accepts.

The checks raise ProviderResponseError inside the backend call, so callers get a typed
`bad_response` ProviderError and the fallback chain moves on, ending in typed input.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from harness.providers.base import Provider, ProviderResponseError, Result, safe_call

MAX_AUDIO_SECONDS = 30
DURATION_TOLERANCE_S = 1.0
MAX_AUDIO_BYTES = 4_000_000
MIN_AUDIO_BYTES = 1_000
AGRI_PROMPT = (
    "urea, DAP, tomato, tamatar, pani, spray, bori, tanki, khad, patta peela, gandum, kapas"
)


@dataclass(frozen=True)
class AudioFormat:
    """How a clip is labelled on upload, so the declared format matches the bytes."""

    container: str
    filename: str
    mime_type: str


FORMATS: dict[str, AudioFormat] = {
    fmt.container: fmt
    for fmt in (
        AudioFormat("webm", "clip.webm", "audio/webm"),  # Chrome, Edge, Android; Matroska too
        AudioFormat("ogg", "clip.ogg", "audio/ogg"),  # Firefox
        AudioFormat("mp4", "clip.m4a", "audio/mp4"),  # Safari, iOS
        AudioFormat("wav", "clip.wav", "audio/wav"),
        AudioFormat("mp3", "clip.mp3", "audio/mpeg"),
        AudioFormat("flac", "clip.flac", "audio/flac"),
    )
}


def _is_mpeg_audio_frame(head: bytes) -> bool:
    """An MPEG audio frame header (MP3 without an ID3 tag). AAC ADTS (layer bits 00) is not."""
    if len(head) < 3 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return False
    version, layer = (head[1] >> 3) & 0b11, (head[1] >> 1) & 0b11
    bitrate, sample_rate = head[2] >> 4, (head[2] >> 2) & 0b11
    return version != 0b01 and layer != 0b00 and bitrate != 0b1111 and sample_rate != 0b11


def sniff_container(audio: bytes) -> AudioFormat | None:
    """Identify the container from its magic bytes; None when it is not a supported one."""
    head = bytes(audio[:12])
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML header: WebM or Matroska
        return FORMATS["webm"]
    if head.startswith(b"OggS"):
        return FORMATS["ogg"]
    if head[4:8] == b"ftyp":  # ISO base media file: MP4, M4A
        return FORMATS["mp4"]
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return FORMATS["wav"]
    if head.startswith(b"fLaC"):
        return FORMATS["flac"]
    if head.startswith(b"ID3") or _is_mpeg_audio_frame(head):
        return FORMATS["mp3"]
    return None


def check_audio(audio: bytes) -> AudioFormat:
    """Reject empty, tiny, oversized or unrecognised clips before any upload or model load."""
    if not audio:
        raise ProviderResponseError("audio is empty")
    if len(audio) < MIN_AUDIO_BYTES:
        raise ProviderResponseError("audio is too short to transcribe")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ProviderResponseError(f"audio is larger than {MAX_AUDIO_BYTES:,} bytes")
    fmt = sniff_container(audio)
    if fmt is None:
        raise ProviderResponseError("unsupported audio format")
    return fmt


def check_duration(seconds: object) -> float:
    """Enforce the clip limit on the duration a backend measured after decoding."""
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds < 0
    ):
        raise ProviderResponseError("audio duration unknown")
    if seconds > MAX_AUDIO_SECONDS + DURATION_TOLERANCE_S:
        raise ProviderResponseError(f"audio is longer than {MAX_AUDIO_SECONDS} s")
    return float(seconds)


def clean_transcript(text: object) -> str:
    """Strip the transcript. An empty one is an error, so the farmer is offered typed input."""
    if not isinstance(text, str):
        raise ProviderResponseError("transcript missing from response")
    text = text.strip()
    if not text:
        raise ProviderResponseError("no speech recognized")
    return text


class STTProvider(Provider, ABC):
    """Backends implement `_transcribe` with the checks above; `transcribe` never raises."""

    name = "stt"

    @abstractmethod
    def _transcribe(self, audio: bytes, language: str, initial_prompt: str) -> str: ...

    def transcribe(
        self, audio: bytes, language: str = "ur", initial_prompt: str = AGRI_PROMPT
    ) -> Result[str]:
        return safe_call(self.name, self._transcribe, audio, language, initial_prompt,
                         timeout=self.timeout_s)
