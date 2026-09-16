from __future__ import annotations

import re

STT_MODELS = [
    {"id": "tiny.en", "name": "Whisper Tiny English", "provider": "faster-whisper", "size": "~75 MB"},
    {"id": "base.en", "name": "Whisper Base English", "provider": "faster-whisper", "size": "~145 MB"},
    {"id": "small.en", "name": "Whisper Small English", "provider": "faster-whisper", "size": "~465 MB"},
]

LLM_MODELS = [
    {"id": "qwen3:14b", "name": "Qwen 3 14B", "provider": "ollama", "size": "~9.3 GB"},
    {"id": "gemma2:2b", "name": "Gemma 2 2B", "provider": "ollama", "size": "~1.6 GB"},
    {"id": "llama3.2:latest", "name": "Llama 3.2", "provider": "ollama", "size": "~2.0 GB"},
]

TTS_CONFIGS = [
    {"id": "af_heart", "name": "Kokoro Heart", "provider": "kokoro", "language": "American English"},
    {"id": "af_sky", "name": "Kokoro Sky", "provider": "kokoro", "language": "American English"},
    {"id": "am_adam", "name": "Kokoro Adam", "provider": "kokoro", "language": "American English"},
]


def normalize_text(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = normalize_text(reference)
    actual = normalize_text(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for index, expected_word in enumerate(expected, start=1):
        current = [index]
        for offset, actual_word in enumerate(actual, start=1):
            current.append(min(current[-1] + 1, previous[offset] + 1,
                               previous[offset - 1] + (expected_word != actual_word)))
        previous = current
    return previous[-1] / len(expected)


def benchmark_transcript(expected: str, actual: str, latency_ms: float) -> dict[str, object]:
    wer = word_error_rate(expected, actual)
    return {
        "expected_text": expected,
        "word_error_rate": round(wer, 4),
        "accuracy_percent": round(max(0.0, (1.0 - wer) * 100), 2),
        "latency_ms": round(latency_ms, 2),
        "passed": wer <= 0.2,
    }


def keyword_coverage(expected_keywords: list[str], response: str) -> float:
    if not expected_keywords:
        return 1.0
    normalized = " ".join(normalize_text(response))
    matches = sum(" ".join(normalize_text(keyword)) in normalized for keyword in expected_keywords)
    return matches / len(expected_keywords)


def real_time_factor(generation_seconds: float, audio_seconds: float) -> float:
    if audio_seconds <= 0:
        return 0.0
    return generation_seconds / audio_seconds
