from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from .domain import Evidence, NodeStatus
from .simulator import ClusterSimulator


Tool = Callable[..., Evidence]


class ClusterTools:
    def __init__(self, cluster: ClusterSimulator) -> None:
        self.cluster = cluster

    def get_cluster_summary(self) -> Evidence:
        state = self.cluster.snapshot()
        unhealthy = [node.id for node in state.nodes if node.status != NodeStatus.HEALTHY]
        return Evidence(
            id=f"ev-{uuid4().hex[:8]}",
            source="cluster_summary",
            summary=f"{len(state.nodes) - len(unhealthy)}/{len(state.nodes)} nodes healthy",
            data={"healthy_nodes": len(state.nodes) - len(unhealthy), "total_nodes": len(state.nodes), "unhealthy_nodes": unhealthy},
        )

    def get_inference_metrics(self) -> Evidence:
        metrics = self.cluster.snapshot().inference
        return Evidence(
            id=f"ev-{uuid4().hex[:8]}",
            source="inference_metrics",
            summary=f"TTFT is {metrics.time_to_first_token_ms} ms; queue depth is {metrics.queue_depth}",
            data=metrics.model_dump(),
        )

    def get_node_health(self, node_id: str) -> Evidence:
        node = next((item for item in self.cluster.snapshot().nodes if item.id == node_id), None)
        if node is None:
            raise ValueError(f"Unknown node: {node_id}")
        return Evidence(
            id=f"ev-{uuid4().hex[:8]}",
            source="node_health",
            summary=f"{node.id} is {node.status} at {node.temperature_c}°C",
            data=node.model_dump(mode="json"),
        )

    def execute(self, name: str, arguments: dict[str, Any]) -> Evidence:
        # Models sometimes emit familiar function notation (for example,
        # ``get_cluster_summary()``) even when only the bare tool name is valid.
        name = name.strip()
        if name.endswith("()"):
            name = name[:-2]

        registry: dict[str, Tool] = {
            "get_cluster_summary": self.get_cluster_summary,
            "get_inference_metrics": self.get_inference_metrics,
            "get_node_health": self.get_node_health,
        }
        if name not in registry:
            raise ValueError(f"Unknown tool: {name}")
        return registry[name](**arguments)
