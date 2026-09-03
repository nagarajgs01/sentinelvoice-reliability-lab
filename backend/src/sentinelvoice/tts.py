from __future__ import annotations

from io import BytesIO
from threading import Lock
from time import perf_counter

import numpy as np
import soundfile as sf

from .config import settings


class KokoroSpeechService:
    """Lazy, process-wide Kokoro adapter that returns 24 kHz WAV audio."""

    sample_rate = 24_000
    max_characters = 800

    def __init__(self) -> None:
        self._pipeline = None
        self._load_lock = Lock()
        self._generation_lock = Lock()

    def _get_pipeline(self):
        if self._pipeline is None:
            with self._load_lock:
                if self._pipeline is None:
                    from kokoro import KPipeline

                    self._pipeline = KPipeline(lang_code="a")
        return self._pipeline

    def synthesize(self, text: str) -> tuple[bytes, float, float]:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            raise ValueError("Speech text is empty")
        if len(cleaned) > self.max_characters:
            raise ValueError(
                f"Speech text exceeds {self.max_characters} characters"
            )

        started = perf_counter()
        with self._generation_lock:
            chunks = [
                np.asarray(audio, dtype=np.float32)
                for _, _, audio in self._get_pipeline()(
                    cleaned,
                    voice=settings.kokoro_voice,
                    speed=1.05,
                )
            ]
        if not chunks:
            raise RuntimeError("Kokoro generated no audio")

        waveform = np.concatenate(chunks)
        output = BytesIO()
        sf.write(output, waveform, self.sample_rate, format="WAV")
        generation_seconds = perf_counter() - started
        audio_seconds = len(waveform) / self.sample_rate
        return output.getvalue(), generation_seconds, audio_seconds


speech_service = KokoroSpeechService()
