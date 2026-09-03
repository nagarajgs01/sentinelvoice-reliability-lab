# SentinelVoice

SentinelVoice is a local-first Voice AI SRE for GPU inference infrastructure. It listens with Silero VAD, transcribes with Whisper, reasons and calls typed tools through Ollama, and speaks with Kokoro TTS.

## Current milestone

The initial scaffold contains the typed backend, a deterministic GPU-cluster simulator, incident tools, and pluggable model adapters. The next milestone connects browser microphone streaming and the React dashboard.

## Architecture

```text
microphone -> Silero VAD -> Whisper -> Ollama agent -> typed tools
                                                    -> Kokoro TTS -> audio
```

## Quick start (development fallback)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn sentinelvoice.main:app --reload
```

Open `http://localhost:8000/docs`. The health and simulation endpoints work without downloading models.

## Run tests

```bash
cd backend
pytest
```

All displayed GPU telemetry is simulated and is not affiliated with or sourced from any cloud provider.

