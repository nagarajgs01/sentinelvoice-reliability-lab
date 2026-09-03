from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NodeStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    DRAINING = "draining"
    QUARANTINED = "quarantined"


class GPUNode(BaseModel):
    id: str
    model: str = "H100"
    status: NodeStatus = NodeStatus.HEALTHY
    temperature_c: float
    utilization_percent: float
    memory_used_gb: float
    memory_total_gb: float = 80
    ecc_errors: int = 0
    active_workloads: int = 16


class InferenceMetrics(BaseModel):
    time_to_first_token_ms: int = 420
    queue_depth: int = 12
    error_rate_percent: float = 0.8
    throughput_requests_sec: float = 118


class ClusterState(BaseModel):
    nodes: list[GPUNode]
    inference: InferenceMetrics = Field(default_factory=InferenceMetrics)
    scenario: str = "healthy"
    updated_at: datetime = Field(default_factory=utc_now)


class Evidence(BaseModel):
    id: str
    source: str
    summary: str
    data: dict[str, Any]
    observed_at: datetime = Field(default_factory=utc_now)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    spoken_response: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    requires_confirmation: bool = False


class RemediationOption(BaseModel):
    action_id: str
    title: str
    description: str
    risk: str
    reversible: bool
    recommended: bool = False
    available: bool = True
    blocked_reason: str | None = None


class PreparedAction(BaseModel):
    confirmation_token: str
    action_id: str
    confirmation_phrase: str
    expires_at: datetime


class ExecutionResult(BaseModel):
    action_id: str
    status: str
    summary: str
    before: InferenceMetrics
    after: InferenceMetrics
    recovered: bool
