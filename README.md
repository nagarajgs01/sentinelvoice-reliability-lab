# SentinelVoice Lab

A local-first Voice AI benchmarking and reliability platform for comparing STT, LLM, TTS, and complete voice pipelines on identical inputs.

## What is implemented

### STT Lab

- Record or upload labeled voice samples
- Run a model × sample batch across Whisper Tiny, Base, and Small
- Measure WER, accuracy, latency, pass rate, and aggregate ranking

### TTS Lab

- Generate identical text with multiple Kokoro voice configurations
- Measure generation latency, audio duration, real-time factor, and round-trip intelligibility
- Listen to every output and run a manual playback interruption test

### Full Pipeline

- Record a real request
- Select Whisper STT, an installed Ollama LLM, and a Kokoro voice
- Run STT → LLM → TTS locally
- Inspect the transcript, response, audio, and component/end-to-end latency

## Models

- STT: Faster Whisper `tiny.en`, `base.en`, `small.en`
- LLM: Ollama `qwen3:14b`, `gemma2:2b`, `llama3.2`
- TTS: Kokoro `af_heart`, `af_sky`, `am_adam`

The first use of a Whisper model downloads its weights. Ollama models must already be installed.

## Run locally

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[voice,dev]"
pytest
uvicorn sentinelvoice.main:app --reload
```

In another terminal:

```bash
cd frontend
nvm use 22
npm install
npm run dev
```

Open `http://localhost:5173`.

## Evaluation methodology

- STT quality uses normalized word error rate against human-provided reference transcripts.
- TTS intelligibility uses ASR round-trip transcription; it is a proxy, not a human naturalness score.
- TTS responsiveness uses generation latency and real-time factor.
- Pipeline runs use correlated component timing across STT, LLM, and TTS.
- Interruption currently measures explicit playback cancellation. Automated acoustic/VAD barge-in is future work.

## Stack

Python, FastAPI, React, TypeScript, Faster Whisper, Ollama, Kokoro, PyTorch, HTTPX, and Pytest.

## Extension points

Provider registries isolate model selection from evaluation logic. Additional local or cloud adapters can be added without changing test datasets or metric definitions.
