import pytest

from sentinelvoice.simulator import ClusterSimulator
from sentinelvoice.tools import ClusterTools


def test_tools_return_structured_evidence() -> None:
    simulator = ClusterSimulator()
    simulator.inject_thermal_failure()
    tools = ClusterTools(simulator)

    evidence = tools.get_node_health("gpu-node-03")

    assert evidence.source == "node_health"
    assert evidence.data["status"] == "failed"
    assert evidence.data["temperature_c"] == 96


def test_unknown_tool_is_rejected() -> None:
    tools = ClusterTools(ClusterSimulator())
    with pytest.raises(ValueError, match="Unknown tool"):
        tools.execute("delete_everything", {})

