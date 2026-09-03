from __future__ import annotations

from copy import deepcopy

from .domain import ClusterState, GPUNode, InferenceMetrics, NodeStatus, utc_now


def healthy_cluster() -> ClusterState:
    temperatures = [69, 72, 70, 73, 68, 71, 70, 72]
    utilizations = [78, 76, 80, 83, 75, 71, 79, 74]
    return ClusterState(
        nodes=[
            GPUNode(
                id=f"gpu-node-{index:02d}",
                temperature_c=temperatures[index - 1],
                utilization_percent=utilizations[index - 1],
                memory_used_gb=round(utilizations[index - 1] * 0.78, 1),
            )
            for index in range(1, 9)
        ]
    )


class ClusterSimulator:
    def __init__(self) -> None:
        self._state = healthy_cluster()

    def snapshot(self) -> ClusterState:
        return deepcopy(self._state)

    def reset(self) -> ClusterState:
        self._state = healthy_cluster()
        return self.snapshot()

    def inject_thermal_failure(self) -> ClusterState:
        node = self._find_node("gpu-node-03")
        node.temperature_c = 96
        node.status = NodeStatus.FAILED
        node.utilization_percent = 0
        node.memory_used_gb = 0
        node.active_workloads = 0
        self._state.inference = InferenceMetrics(
            time_to_first_token_ms=2840,
            queue_depth=146,
            error_rate_percent=8.7,
            throughput_requests_sec=74,
        )
        self._state.scenario = "thermal_failure"
        self._state.updated_at = utc_now()
        return self.snapshot()

    def inject_traffic_spike(self) -> ClusterState:
        for node in self._state.nodes:
            node.utilization_percent = min(98, node.utilization_percent + 17)
            node.temperature_c += 5
        self._state.inference = InferenceMetrics(
            time_to_first_token_ms=1760,
            queue_depth=204,
            error_rate_percent=2.1,
            throughput_requests_sec=281,
        )
        self._state.scenario = "traffic_spike"
        self._state.updated_at = utc_now()
        return self.snapshot()

    def drain_and_redistribute(self, node_id: str) -> ClusterState:
        node = self._find_node(node_id)
        if node.status != NodeStatus.FAILED:
            raise ValueError(f"Node is not failed: {node_id}")

        node.status = NodeStatus.QUARANTINED
        node.active_workloads = 0
        for destination in self._state.nodes:
            if destination.status == NodeStatus.HEALTHY:
                destination.utilization_percent = min(
                    88,
                    destination.utilization_percent + 4,
                )
                destination.active_workloads += 2

        self._state.inference = InferenceMetrics(
            time_to_first_token_ms=540,
            queue_depth=24,
            error_rate_percent=1.1,
            throughput_requests_sec=112,
        )
        self._state.scenario = "thermal_failure_mitigated"
        self._state.updated_at = utc_now()
        return self.snapshot()

    def reduce_traffic(self) -> ClusterState:
        self._state.inference = InferenceMetrics(
            time_to_first_token_ms=820,
            queue_depth=38,
            error_rate_percent=1.6,
            throughput_requests_sec=82,
        )
        self._state.scenario = f"{self._state.scenario}_traffic_reduced"
        self._state.updated_at = utc_now()
        return self.snapshot()

    def _find_node(self, node_id: str) -> GPUNode:
        for node in self._state.nodes:
            if node.id == node_id:
                return node
        raise ValueError(f"Unknown node: {node_id}")


simulator = ClusterSimulator()
