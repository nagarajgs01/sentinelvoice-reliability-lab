from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock


class WhisperRegistry:
    """Lazy cache of selectable Faster Whisper models."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._lock = Lock()

    def _get_model(self, model_name: str):
        if model_name not in self._models:
            with self._lock:
                if model_name not in self._models:
                    from faster_whisper import WhisperModel
                    self._models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
        return self._models[model_name]

    def transcribe_bytes(self, model_name: str, audio: bytes, suffix: str = ".webm") -> dict[str, object]:
        if not audio:
            raise ValueError("Audio payload is empty")
        path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(audio)
                path = Path(temporary.name)
            segments, info = self._get_model(model_name).transcribe(str(path), beam_size=1, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return {"text": text, "language": info.language, "duration_seconds": round(info.duration, 3)}
        finally:
            if path is not None:
                path.unlink(missing_ok=True)


transcribers = WhisperRegistry()
