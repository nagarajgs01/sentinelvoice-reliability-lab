from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from .config import settings


class WhisperTranscriber:
    """Lazy, process-wide Faster Whisper adapter for uploaded audio."""

    def __init__(self) -> None:
        self._model = None
        self._lock = Lock()

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    self._model = WhisperModel(
                        settings.whisper_model,
                        device="cpu",
                        compute_type="int8",
                    )
        return self._model

    def transcribe_bytes(self, audio: bytes, suffix: str = ".webm") -> dict[str, object]:
        if not audio:
            raise ValueError("Audio payload is empty")

        path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(audio)
                path = Path(temporary.name)

            segments, info = self._get_model().transcribe(
                str(path),
                beam_size=1,
                vad_filter=True,
            )
            materialized = list(segments)
            text = " ".join(segment.text.strip() for segment in materialized).strip()
            return {
                "text": text,
                "language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration_seconds": round(info.duration, 3),
            }
        finally:
            if path is not None:
                path.unlink(missing_ok=True)


transcriber = WhisperTranscriber()

