from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .tracing import TraceEvent, TraceRecord


class MetricResult(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    threshold: float | None = None
    comparator: str | None = None
    status: Literal["pass", "fail", "not_measured", "info"]
    critical: bool = False
    evidence_event_ids: list[str] = Field(default_factory=list)
    explanation: str


class EvaluationReport(BaseModel):
    trace_id: str
    status: Literal["pass", "fail", "incomplete"]
    score: float
    passed_metrics: int
    failed_metrics: int
    missing_metrics: int
    metrics: list[MetricResult]


THRESHOLDS_MS = {
    "stt_latency": 1_000.0,
    "llm_total": 5_000.0,
    "tool_total": 250.0,
    "agent_processing": 6_000.0,
    "tts_generation": 1_500.0,
    "time_to_first_audio": 7_000.0,
    "interruption_latency": 300.0,
}


def events_for(trace: TraceRecord, component: str, name: str | None = None) -> list[TraceEvent]:
    return [
        event
        for event in trace.events
        if event.component == component and (name is None or event.name == name)
    ]


def latency_metric(
    key: str,
    label: str,
    events: list[TraceEvent],
    *,
    critical: bool = True,
) -> MetricResult:
    measured = [event for event in events if event.duration_ms is not None]
    threshold = THRESHOLDS_MS[key]
    if not measured:
        return MetricResult(
            key=key,
            label=label,
            value=None,
            unit="ms",
            threshold=threshold,
            comparator="<=",
            status="not_measured",
            critical=critical,
            explanation="Required trace event was not captured.",
        )
    value = round(sum(event.duration_ms or 0 for event in measured), 3)
    passed = value <= threshold
    return MetricResult(
        key=key,
        label=label,
        value=value,
        unit="ms",
        threshold=threshold,
        comparator="<=",
        status="pass" if passed else "fail",
        critical=critical,
        evidence_event_ids=[event.event_id for event in measured],
        explanation=(
            f"{value:.1f} ms is within the {threshold:.0f} ms threshold."
            if passed
            else f"{value:.1f} ms exceeds the {threshold:.0f} ms threshold."
        ),
    )


def delta_metric(
    key: str,
    label: str,
    start: TraceEvent | None,
    end: TraceEvent | None,
) -> MetricResult:
    threshold = THRESHOLDS_MS[key]
    if start is None or end is None:
        return MetricResult(
            key=key,
            label=label,
            value=None,
            unit="ms",
            threshold=threshold,
            comparator="<=",
            status="not_measured",
            critical=True,
            explanation="Start or end event was not captured.",
        )
    value = round(max(0.0, end.elapsed_ms - start.elapsed_ms), 3)
    passed = value <= threshold
    return MetricResult(
        key=key,
        label=label,
        value=value,
        unit="ms",
        threshold=threshold,
        comparator="<=",
        status="pass" if passed else "fail",
        critical=True,
        evidence_event_ids=[start.event_id, end.event_id],
        explanation=(
            f"{value:.1f} ms is within the {threshold:.0f} ms threshold."
            if passed
            else f"{value:.1f} ms exceeds the {threshold:.0f} ms threshold."
        ),
    )


def evaluate_trace(trace: TraceRecord) -> EvaluationReport:
    turn_started = next(iter(events_for(trace, "orchestrator", "turn_started")), None)
    playback_started = next(iter(events_for(trace, "playback", "playback_started")), None)
    interruption_stopped = events_for(trace, "playback", "interruption_stopped")

    metrics = [
        latency_metric("stt_latency", "STT latency", events_for(trace, "stt", "transcription"), critical=False),
        latency_metric("llm_total", "LLM total latency", events_for(trace, "llm")),
        latency_metric("tool_total", "Tool latency", events_for(trace, "tool")),
        latency_metric("agent_processing", "Agent processing", events_for(trace, "orchestrator", "turn_completed")),
        latency_metric("tts_generation", "TTS generation", events_for(trace, "tts", "speech_generation")),
        delta_metric("time_to_first_audio", "Time to first audio", turn_started, playback_started),
        latency_metric("interruption_latency", "Interruption stop latency", interruption_stopped, critical=False),
    ]

    measured = [metric for metric in metrics if metric.status in {"pass", "fail"}]
    passed = [metric for metric in measured if metric.status == "pass"]
    failed = [metric for metric in measured if metric.status == "fail"]
    missing = [metric for metric in metrics if metric.status == "not_measured"]
    critical_failures = [metric for metric in failed if metric.critical]
    critical_missing = [metric for metric in missing if metric.critical]

    status: Literal["pass", "fail", "incomplete"]
    if critical_failures:
        status = "fail"
    elif critical_missing:
        status = "incomplete"
    else:
        status = "pass"

    score = round((len(passed) / len(measured) * 100) if measured else 0.0, 1)
    return EvaluationReport(
        trace_id=trace.trace_id,
        status=status,
        score=score,
        passed_metrics=len(passed),
        failed_metrics=len(failed),
        missing_metrics=len(missing),
        metrics=metrics,
    )
