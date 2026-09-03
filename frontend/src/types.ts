export type NodeStatus = "healthy" | "degraded" | "failed" | "draining" | "quarantined";

export interface GPUNode {
  id: string;
  model: string;
  status: NodeStatus;
  temperature_c: number;
  utilization_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  ecc_errors: number;
  active_workloads: number;
}

export interface ClusterState {
  nodes: GPUNode[];
  inference: {
    time_to_first_token_ms: number;
    queue_depth: number;
    error_rate_percent: number;
    throughput_requests_sec: number;
  };
  scenario: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  source: string;
  summary: string;
  data: Record<string, unknown>;
}

export interface RemediationOption {
  action_id: string;
  title: string;
  description: string;
  risk: string;
  reversible: boolean;
  recommended: boolean;
  available: boolean;
  blocked_reason: string | null;
}

export interface PreparedAction {
  confirmation_token: string;
  action_id: string;
  confirmation_phrase: string;
  expires_at: string;
}

export interface TraceEvent {
  event_id: string;
  trace_id: string;
  component: string;
  name: string;
  timestamp: string;
  elapsed_ms: number;
  duration_ms: number | null;
  status: string;
  metadata: Record<string, unknown>;
}

export interface TraceRecord {
  trace_id: string;
  started_at: string;
  events: TraceEvent[];
  total_elapsed_ms: number;
  component_latency_ms: Record<string, number>;
}

export interface MetricResult {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  threshold: number | null;
  comparator: string | null;
  status: "pass" | "fail" | "not_measured" | "info";
  critical: boolean;
  evidence_event_ids: string[];
  explanation: string;
}

export interface EvaluationReport {
  trace_id: string;
  status: "pass" | "fail" | "incomplete";
  score: number;
  passed_metrics: number;
  failed_metrics: number;
  missing_metrics: number;
  metrics: MetricResult[];
}
