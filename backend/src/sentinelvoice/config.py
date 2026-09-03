from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    whisper_model: str = os.getenv("WHISPER_MODEL", "tiny.en")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    kokoro_voice: str = os.getenv("KOKORO_VOICE", "af_heart")
    sample_rate: int = 16_000
    vad_threshold: float = float(os.getenv("VAD_THRESHOLD", "0.55"))
    development_fallbacks: bool = os.getenv("DEVELOPMENT_FALLBACKS", "true").lower() == "true"


settings = Settings()
