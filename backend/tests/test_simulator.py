from sentinelvoice.simulator import ClusterSimulator


def test_thermal_failure_degrades_inference() -> None:
    simulator = ClusterSimulator()
    before = simulator.snapshot()
    after = simulator.inject_thermal_failure()

    node = next(item for item in after.nodes if item.id == "gpu-node-03")
    assert node.status == "failed"
    assert node.temperature_c == 96
    assert after.inference.time_to_first_token_ms > before.inference.time_to_first_token_ms
    assert after.inference.queue_depth > before.inference.queue_depth


def test_traffic_spike_does_not_mark_nodes_failed() -> None:
    simulator = ClusterSimulator()
    after = simulator.inject_traffic_spike()

    assert all(node.status == "healthy" for node in after.nodes)
    assert after.inference.queue_depth == 204

