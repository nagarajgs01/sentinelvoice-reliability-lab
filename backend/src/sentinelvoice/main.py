from __future__ import annotations

import base64
from time import perf_counter

import httpx

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .benchmark import (
    LLM_MODELS,
    STT_MODELS,
    TTS_CONFIGS,
    benchmark_transcript,
    keyword_coverage,
    real_time_factor,
)
from .evaluation import evaluate_trace
from .transcription import transcribers
from .tts import speech_service
from .tracing import traces
from .ollama import ollama_service

app = FastAPI(title="SentinelVoice Lab API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def request_trace_id(request: Request) -> str:
    return traces.ensure(request.headers.get("x-trace-id"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "SentinelVoice Lab"}


@app.get("/api/models")
def models():
    return {"stt": STT_MODELS, "llm": LLM_MODELS, "tts": TTS_CONFIGS}


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str):
    trace = traces.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@app.get("/api/traces/{trace_id}/evaluation")
def get_trace_evaluation(trace_id: str):
    trace = traces.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return evaluate_trace(trace)


@app.post("/api/traces/{trace_id}/events")
def record_client_trace_event(trace_id: str, payload: dict):
    trace_id = traces.ensure(trace_id)
    return traces.record(
        trace_id,
        str(payload.get("component", "client"))[:40],
        str(payload.get("name", "event"))[:80],
        duration_ms=payload.get("duration_ms"),
        status=str(payload.get("status", "ok"))[:20],
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


@app.post("/api/benchmarks/stt")
async def benchmark_stt(
    request: Request,
    model: str = Query(...),
    expected_text: str = Query(..., min_length=1),
):
    if model not in {item["id"] for item in STT_MODELS}:
        raise HTTPException(status_code=404, detail=f"Unknown STT model: {model}")
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio payload is empty")
    content_type = request.headers.get("content-type", "audio/webm").split(";", 1)[0]
    suffix = {"audio/webm": ".webm", "audio/mp4": ".mp4", "audio/wav": ".wav", "audio/x-wav": ".wav"}.get(content_type, ".webm")
    trace_id = request_trace_id(request)
    started = perf_counter()
    result = await run_in_threadpool(transcribers.transcribe_bytes, model, audio, suffix)
    latency_ms = (perf_counter() - started) * 1000
    traces.record(
        trace_id, "stt", "transcription", duration_ms=latency_ms,
        metadata={"model": model, "audio_bytes": len(audio)},
    )
    return {
        **benchmark_transcript(expected_text, str(result["text"]), latency_ms),
        **result, "model": model, "trace_id": trace_id,
    }


@app.post("/api/voice/speak")
async def synthesize_speech(payload: dict[str, str], request: Request):
    trace_id = request_trace_id(request)
    try:
        audio, generation_seconds, audio_seconds = await run_in_threadpool(
            speech_service.synthesize, payload.get("text", ""), payload.get("voice")
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    traces.record(
        trace_id, "tts", "speech_generation", duration_ms=generation_seconds * 1000,
        metadata={"audio_duration_seconds": round(audio_seconds, 3)},
    )
    return Response(content=audio, media_type="audio/wav", headers={"X-Trace-ID": trace_id})


@app.post("/api/benchmarks/tts")
async def benchmark_tts(payload: dict, request: Request):
    text = str(payload.get("text", "")).strip()
    voice = str(payload.get("voice", ""))
    stt_model = str(payload.get("stt_model", "tiny.en"))
    if voice not in {item["id"] for item in TTS_CONFIGS}:
        raise HTTPException(status_code=404, detail=f"Unknown TTS voice: {voice}")
    if stt_model not in {item["id"] for item in STT_MODELS}:
        raise HTTPException(status_code=404, detail=f"Unknown STT model: {stt_model}")
    trace_id = request_trace_id(request)
    try:
        audio, generation_seconds, audio_seconds = await run_in_threadpool(
            speech_service.synthesize, text, voice
        )
        transcription = await run_in_threadpool(
            transcribers.transcribe_bytes, stt_model, audio, ".wav"
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    quality = benchmark_transcript(text, str(transcription["text"]), generation_seconds * 1000)
    traces.record(trace_id, "tts", "speech_generation", duration_ms=generation_seconds * 1000,
                  metadata={"voice": voice, "audio_duration_seconds": audio_seconds})
    return {
        "voice": voice,
        "text": text,
        "round_trip_transcript": transcription["text"],
        "intelligibility_percent": quality["accuracy_percent"],
        "word_error_rate": quality["word_error_rate"],
        "generation_ms": round(generation_seconds * 1000, 2),
        "audio_seconds": round(audio_seconds, 3),
        "real_time_factor": round(real_time_factor(generation_seconds, audio_seconds), 3),
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "trace_id": trace_id,
    }


@app.post("/api/benchmarks/llm")
async def benchmark_llm(payload: dict, request: Request):
    model = str(payload.get("model", ""))
    prompt = str(payload.get("prompt", ""))
    keywords = [str(item) for item in payload.get("expected_keywords", [])]
    if model not in {item["id"] for item in LLM_MODELS}:
        raise HTTPException(status_code=404, detail=f"Unknown LLM model: {model}")
    trace_id = request_trace_id(request)
    try:
        response, duration = await ollama_service.complete(model, prompt)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(status_code=503, detail=f"Ollama request failed: {error}") from error
    coverage = keyword_coverage(keywords, response)
    traces.record(trace_id, "llm", "completion", duration_ms=duration * 1000,
                  metadata={"model": model, "keyword_coverage": coverage})
    return {"model": model, "response": response, "latency_ms": round(duration * 1000, 2),
            "keyword_coverage_percent": round(coverage * 100, 2), "passed": coverage >= 0.8,
            "trace_id": trace_id}


@app.post("/api/benchmarks/pipeline")
async def benchmark_pipeline(
    request: Request,
    stt_model: str = Query(...),
    llm_model: str = Query(...),
    tts_voice: str = Query(...),
    expected_transcript: str = Query(..., min_length=1),
):
    if stt_model not in {item["id"] for item in STT_MODELS}:
        raise HTTPException(status_code=404, detail=f"Unknown STT model: {stt_model}")
    if llm_model not in {item["id"] for item in LLM_MODELS}:
        raise HTTPException(status_code=404, detail=f"Unknown LLM model: {llm_model}")
    if tts_voice not in {item["id"] for item in TTS_CONFIGS}:
        raise HTTPException(status_code=404, detail=f"Unknown TTS voice: {tts_voice}")
    source_audio = await request.body()
    if not source_audio:
        raise HTTPException(status_code=400, detail="Audio payload is empty")
    trace_id = request_trace_id(request)
    content_type = request.headers.get("content-type", "audio/webm").split(";", 1)[0]
    suffix = {"audio/mp4": ".mp4", "audio/wav": ".wav", "audio/x-wav": ".wav"}.get(content_type, ".webm")
    stt_started = perf_counter()
    transcript = await run_in_threadpool(transcribers.transcribe_bytes, stt_model, source_audio, suffix)
    stt_ms = (perf_counter() - stt_started) * 1000
    response, llm_seconds = await ollama_service.complete(llm_model, str(transcript["text"]))
    response_audio, tts_seconds, audio_seconds = await run_in_threadpool(
        speech_service.synthesize, response, tts_voice
    )
    transcript_quality = benchmark_transcript(expected_transcript, str(transcript["text"]), stt_ms)
    traces.record(trace_id, "stt", "transcription", duration_ms=stt_ms, metadata={"model": stt_model})
    traces.record(trace_id, "llm", "completion", duration_ms=llm_seconds * 1000, metadata={"model": llm_model})
    traces.record(trace_id, "tts", "speech_generation", duration_ms=tts_seconds * 1000, metadata={"voice": tts_voice})
    return {
        "configuration": {"stt": stt_model, "llm": llm_model, "tts": tts_voice},
        "transcript": transcript["text"], "response": response,
        "stt_accuracy_percent": transcript_quality["accuracy_percent"],
        "stt_ms": round(stt_ms, 2), "llm_ms": round(llm_seconds * 1000, 2),
        "tts_ms": round(tts_seconds * 1000, 2),
        "total_ms": round(stt_ms + llm_seconds * 1000 + tts_seconds * 1000, 2),
        "response_audio_seconds": round(audio_seconds, 3),
        "audio_base64": base64.b64encode(response_audio).decode("ascii"), "trace_id": trace_id,
    }
