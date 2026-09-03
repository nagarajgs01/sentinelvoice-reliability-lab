from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import json
from time import perf_counter

from .agent import OllamaAgent, OllamaTimeoutError
from .simulator import simulator
from .domain import Evidence, ToolCall
from .evaluation import evaluate_trace
from .remediation import RemediationError, RemediationManager
from .tools import ClusterTools
from .transcription import transcriber
from .tts import speech_service
from .tracing import traces


app = FastAPI(title="SentinelVoice API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tools = ClusterTools(simulator)
agent = OllamaAgent()
remediation = RemediationManager(simulator)
MAX_INVESTIGATION_STEPS = 4


def request_trace_id(request: Request) -> str:
    return traces.ensure(request.headers.get("x-trace-id"))


def execute_tool_traced(trace_id: str, call: ToolCall) -> Evidence:
    started = perf_counter()
    try:
        result = tools.execute(call.name, call.arguments)
    except Exception:
        traces.record(
            trace_id,
            "tool",
            "tool_call",
            duration_ms=(perf_counter() - started) * 1000,
            status="error",
            metadata={"tool": call.name, "arguments": call.arguments},
        )
        raise
    traces.record(
        trace_id,
        "tool",
        "tool_call",
        duration_ms=(perf_counter() - started) * 1000,
        metadata={"tool": call.name, "arguments": call.arguments, "source": result.source},
    )
    return result


def call_signature(call: ToolCall) -> str:
    normalized_name = call.name.strip()
    if normalized_name.endswith("()"):
        normalized_name = normalized_name[:-2]
    return json.dumps(
        {"name": normalized_name, "arguments": call.arguments},
        sort_keys=True,
    )


def required_baseline_calls(transcript: str) -> list[ToolCall]:
    """Require core telemetry for broad incident and latency investigations."""
    investigation_terms = (
        "investigate",
        "incident",
        "latency",
        "root cause",
        "slow",
        "queue",
        "error rate",
    )
    if any(term in transcript.lower() for term in investigation_terms):
        return [
            ToolCall(name="get_cluster_summary"),
            ToolCall(name="get_inference_metrics"),
        ]
    return []


def missing_unhealthy_node_calls(evidence: list[Evidence]) -> list[ToolCall]:
    """Inspect each unhealthy node discovered by cluster-summary evidence."""
    unhealthy_nodes: set[str] = set()
    inspected_nodes: set[str] = set()

    for item in evidence:
        if item.source == "cluster_summary":
            unhealthy_nodes.update(item.data.get("unhealthy_nodes", []))
        elif item.source == "node_health" and item.data.get("id"):
            inspected_nodes.add(item.data["id"])

    return [
        ToolCall(name="get_node_health", arguments={"node_id": node_id})
        for node_id in sorted(unhealthy_nodes - inspected_nodes)
    ]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cluster")
def cluster():
    return simulator.snapshot()


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
    event = traces.record(
        trace_id,
        str(payload.get("component", "client"))[:40],
        str(payload.get("name", "event"))[:80],
        duration_ms=payload.get("duration_ms"),
        status=str(payload.get("status", "ok"))[:20],
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )
    return event


@app.post("/api/scenarios/{scenario}")
def inject_scenario(scenario: str):
    if scenario == "thermal_failure":
        return simulator.inject_thermal_failure()
    if scenario == "traffic_spike":
        return simulator.inject_traffic_spike()
    if scenario == "reset":
        return simulator.reset()
    raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario}")


@app.post("/api/agent/message")
async def message(payload: dict[str, str], request: Request):
    trace_id = request_trace_id(request)
    turn_started = perf_counter()
    traces.record(trace_id, "orchestrator", "turn_started")
    transcript = payload.get("text", "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text is required")
    evidence = []
    executed_calls: set[str] = set()

    for call in required_baseline_calls(transcript):
        executed_calls.add(call_signature(call))
        evidence.append(execute_tool_traced(trace_id, call))

    for _ in range(MAX_INVESTIGATION_STEPS):
        llm_started = perf_counter()
        try:
            decision = await agent.decide(transcript, evidence)
        except OllamaTimeoutError as error:
            traces.record(trace_id, "llm", "decision", duration_ms=(perf_counter() - llm_started) * 1000, status="timeout")
            raise HTTPException(status_code=504, detail=str(error)) from error
        traces.record(
            trace_id,
            "llm",
            "decision",
            duration_ms=(perf_counter() - llm_started) * 1000,
            metadata={"tool_calls_requested": len(decision.tool_calls)},
        )
        if not decision.tool_calls:
            required_node_calls = missing_unhealthy_node_calls(evidence)
            if not required_node_calls:
                break
            for call in required_node_calls:
                executed_calls.add(call_signature(call))
                evidence.append(execute_tool_traced(trace_id, call))
            continue

        new_calls = []
        for call in decision.tool_calls:
            signature = call_signature(call)
            if signature not in executed_calls:
                executed_calls.add(signature)
                new_calls.append(call)

        if not new_calls:
            llm_started = perf_counter()
            try:
                decision = await agent.decide(transcript, evidence, allow_tools=False)
            except OllamaTimeoutError as error:
                raise HTTPException(status_code=504, detail=str(error)) from error
            traces.record(trace_id, "llm", "final_decision", duration_ms=(perf_counter() - llm_started) * 1000)
            break

        for call in new_calls:
            try:
                evidence.append(execute_tool_traced(trace_id, call))
            except (TypeError, ValueError) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
    else:
        llm_started = perf_counter()
        try:
            decision = await agent.decide(transcript, evidence, allow_tools=False)
        except OllamaTimeoutError as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        traces.record(trace_id, "llm", "final_decision", duration_ms=(perf_counter() - llm_started) * 1000)

    traces.record(
        trace_id,
        "orchestrator",
        "turn_completed",
        duration_ms=(perf_counter() - turn_started) * 1000,
        metadata={"evidence_count": len(evidence)},
    )

    return {
        "decision": decision,
        "evidence": evidence,
        "recommendations": remediation.options(),
        "trace_id": trace_id,
    }


@app.get("/api/remediation/options")
def remediation_options():
    return remediation.options()


@app.post("/api/remediation/prepare")
def prepare_remediation(payload: dict[str, str]):
    action_id = payload.get("action_id", "").strip()
    try:
        return remediation.prepare(action_id)
    except RemediationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/remediation/confirm")
def confirm_remediation(payload: dict[str, str]):
    action_id = payload.get("action_id", "").strip()
    token = payload.get("confirmation_token", "").strip()
    try:
        result = remediation.confirm(action_id, token)
    except RemediationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"result": result, "cluster": simulator.snapshot()}


@app.post("/api/remediation/voice-confirm")
def voice_confirm_remediation(payload: dict[str, str]):
    action_id = payload.get("action_id", "").strip()
    token = payload.get("confirmation_token", "").strip()
    phrase = payload.get("phrase", "").strip()
    try:
        result = remediation.confirm_by_phrase(action_id, token, phrase)
    except RemediationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"result": result, "cluster": simulator.snapshot()}


@app.post("/api/remediation/cancel")
def cancel_remediation(payload: dict[str, str]):
    token = payload.get("confirmation_token", "").strip()
    try:
        remediation.cancel(token)
    except RemediationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"status": "cancelled"}


@app.post("/api/voice/transcribe")
async def transcribe_audio(request: Request):
    trace_id = request_trace_id(request)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio payload is empty")

    content_type = request.headers.get("content-type", "audio/webm")
    suffixes = {
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }
    suffix = suffixes.get(content_type.split(";", 1)[0], ".webm")
    started = perf_counter()
    try:
        result = transcriber.transcribe_bytes(audio, suffix=suffix)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    traces.record(
        trace_id,
        "stt",
        "transcription",
        duration_ms=(perf_counter() - started) * 1000,
        metadata={"audio_bytes": len(audio), "language": result.get("language")},
    )
    return {**result, "trace_id": trace_id}


@app.post("/api/voice/speak")
async def synthesize_speech(payload: dict[str, str], request: Request):
    trace_id = request_trace_id(request)
    text = payload.get("text", "")
    try:
        audio, generation_seconds, audio_seconds = await run_in_threadpool(
            speech_service.synthesize,
            text,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    traces.record(
        trace_id,
        "tts",
        "speech_generation",
        duration_ms=generation_seconds * 1000,
        metadata={"audio_duration_seconds": round(audio_seconds, 3), "characters": len(text)},
    )

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-TTS-Generation-Seconds": f"{generation_seconds:.3f}",
            "X-Audio-Duration-Seconds": f"{audio_seconds:.3f}",
            "X-Trace-ID": trace_id,
        },
    )
