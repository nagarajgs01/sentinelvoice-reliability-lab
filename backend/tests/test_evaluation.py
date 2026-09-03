from sentinelvoice.evaluation import evaluate_trace
from sentinelvoice.tracing import TraceStore


def complete_trace(*, llm_ms: float = 800, tts_ms: float = 400):
    store = TraceStore()
    trace_id = store.ensure("evaluation-trace")
    store.record(trace_id, "stt", "transcription", duration_ms=300)
    store.record(trace_id, "orchestrator", "turn_started")
    store.record(trace_id, "tool", "tool_call", duration_ms=10)
    store.record(trace_id, "llm", "decision", duration_ms=llm_ms)
    store.record(trace_id, "orchestrator", "turn_completed", duration_ms=llm_ms + 10)
    store.record(trace_id, "tts", "speech_generation", duration_ms=tts_ms)
    store.record(trace_id, "playback", "playback_started")
    return store.get(trace_id)


def test_fast_trace_passes_quality_gate() -> None:
    trace = complete_trace()
    assert trace is not None

    report = evaluate_trace(trace)

    assert report.status == "pass"
    assert report.failed_metrics == 0


def test_slow_llm_fails_quality_gate() -> None:
    trace = complete_trace(llm_ms=8_000)
    assert trace is not None

    report = evaluate_trace(trace)
    llm = next(metric for metric in report.metrics if metric.key == "llm_total")

    assert report.status == "fail"
    assert llm.status == "fail"
    assert llm.value == 8_000


def test_missing_tts_marks_report_incomplete() -> None:
    store = TraceStore()
    trace_id = store.ensure("incomplete")
    store.record(trace_id, "orchestrator", "turn_started")
    store.record(trace_id, "llm", "decision", duration_ms=200)
    store.record(trace_id, "tool", "tool_call", duration_ms=5)
    store.record(trace_id, "orchestrator", "turn_completed", duration_ms=205)
    trace = store.get(trace_id)
    assert trace is not None

    report = evaluate_trace(trace)

    assert report.status == "incomplete"
    assert report.missing_metrics >= 2
