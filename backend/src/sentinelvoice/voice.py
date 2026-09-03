from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import numpy as np


class SpeechToText(Protocol):
    def transcribe(self, pcm16: bytes, sample_rate: int) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class VoiceActivityDetector(Protocol):
    def probability(self, pcm16: bytes, sample_rate: int) -> float: ...


@dataclass
class VoiceTurn:
    transcript: str
    response_text: str
    response_audio: bytes


class FasterWhisperSTT:
    """Lazy adapter so model weights load only when voice mode starts."""

    def __init__(self, model_name: str = "tiny.en") -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio, beam_size=1, vad_filter=False)
        return " ".join(segment.text.strip() for segment in segments).strip()


class DevelopmentSTT:
    """Explicit fallback for plumbing tests; never presented as model output."""

    def transcribe(self, pcm16: bytes, sample_rate: int) -> str:
        return "development audio received"


class DevelopmentTTS:
    def synthesize(self, text: str) -> bytes:
        return BytesIO(text.encode("utf-8")).getvalue()

