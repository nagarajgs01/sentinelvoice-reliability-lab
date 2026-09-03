from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt-{uuid4().hex[:12]}")
    trace_id: str
    component: str
    name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    elapsed_ms: float
    duration_ms: float | None = None
    status: str = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceRecord(BaseModel):
    trace_id: str
    started_at: datetime
    events: list[TraceEvent]
    total_elapsed_ms: float
    component_latency_ms: dict[str, float]


class TraceStore:
    """Bounded in-memory event store for local observability and evaluation."""

    def __init__(self, max_traces: int = 200) -> None:
        self.max_traces = max_traces
        self._lock = Lock()
        self._traces: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def new_trace_id(self) -> str:
        return str(uuid4())

    def ensure(self, trace_id: str | None = None) -> str:
        value = (trace_id or self.new_trace_id()).strip()
        if not value or len(value) > 128:
            value = self.new_trace_id()
        with self._lock:
            if value not in self._traces:
                self._traces[value] = {
                    "started_at": datetime.now(timezone.utc),
                    "started_clock": perf_counter(),
                    "events": [],
                }
                while len(self._traces) > self.max_traces:
                    self._traces.popitem(last=False)
        return value

    def record(
        self,
        trace_id: str,
        component: str,
        name: str,
        *,
        duration_ms: float | None = None,
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        trace_id = self.ensure(trace_id)
        with self._lock:
            trace = self._traces[trace_id]
            event = TraceEvent(
                trace_id=trace_id,
                component=component,
                name=name,
                elapsed_ms=round((perf_counter() - trace["started_clock"]) * 1000, 3),
                duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
                status=status,
                metadata=metadata or {},
            )
            trace["events"].append(event)
            return event

    def get(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return None
            events = list(trace["events"])
            started_at = trace["started_at"]

        totals: dict[str, float] = {}
        for event in events:
            if event.duration_ms is not None:
                totals[event.component] = totals.get(event.component, 0.0) + event.duration_ms
        total = events[-1].elapsed_ms if events else 0.0
        return TraceRecord(
            trace_id=trace_id,
            started_at=started_at,
            events=events,
            total_elapsed_ms=round(total, 3),
            component_latency_ms={key: round(value, 3) for key, value in totals.items()},
        )


traces = TraceStore()
