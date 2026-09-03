from sentinelvoice.domain import Evidence
from sentinelvoice.main import missing_unhealthy_node_calls, required_baseline_calls


def test_latency_investigation_requires_baseline_evidence() -> None:
    calls = required_baseline_calls("Investigate the high inference latency")

    assert [call.name for call in calls] == [
        "get_cluster_summary",
        "get_inference_metrics",
    ]


def test_unhealthy_nodes_must_be_inspected() -> None:
    evidence = [
        Evidence(
            id="summary",
            source="cluster_summary",
            summary="7/8 nodes healthy",
            data={"unhealthy_nodes": ["gpu-node-03"]},
        )
    ]

    calls = missing_unhealthy_node_calls(evidence)

    assert len(calls) == 1
    assert calls[0].name == "get_node_health"
    assert calls[0].arguments == {"node_id": "gpu-node-03"}


def test_inspected_unhealthy_node_is_not_requested_twice() -> None:
    evidence = [
        Evidence(
            id="summary",
            source="cluster_summary",
            summary="7/8 nodes healthy",
            data={"unhealthy_nodes": ["gpu-node-03"]},
        ),
        Evidence(
            id="node",
            source="node_health",
            summary="gpu-node-03 is failed",
            data={"id": "gpu-node-03"},
        ),
    ]

    assert missing_unhealthy_node_calls(evidence) == []
