from sentinelvoice.tracing import TraceStore


def test_trace_correlates_events_and_aggregates_component_latency() -> None:
    store = TraceStore()
    trace_id = store.ensure("turn-123")

    store.record(trace_id, "stt", "transcription", duration_ms=120.5)
    store.record(trace_id, "llm", "decision", duration_ms=800)
    store.record(trace_id, "llm", "final_decision", duration_ms=200)

    trace = store.get(trace_id)

    assert trace is not None
    assert [event.name for event in trace.events] == [
        "transcription",
        "decision",
        "final_decision",
    ]
    assert trace.component_latency_ms == {"stt": 120.5, "llm": 1000.0}


def test_trace_store_is_bounded() -> None:
    store = TraceStore(max_traces=2)
    store.ensure("first")
    store.ensure("second")
    store.ensure("third")

    assert store.get("first") is None
    assert store.get("second") is not None
    assert store.get("third") is not None


def test_invalid_external_trace_id_is_replaced() -> None:
    store = TraceStore()

    trace_id = store.ensure("x" * 200)

    assert trace_id != "x" * 200
    assert store.get(trace_id) is not None
