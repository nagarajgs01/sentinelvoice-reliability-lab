import pytest

from sentinelvoice.remediation import RemediationError, RemediationManager
from sentinelvoice.simulator import ClusterSimulator


def failed_cluster() -> tuple[ClusterSimulator, RemediationManager]:
    cluster = ClusterSimulator()
    cluster.inject_thermal_failure()
    return cluster, RemediationManager(cluster)


def test_hot_failed_node_blocks_restart() -> None:
    _, manager = failed_cluster()
    restart = next(item for item in manager.options() if item.action_id == "restart_worker")

    assert restart.available is False
    assert "96" in (restart.blocked_reason or "")


def test_confirmed_redistribution_recovers_inference() -> None:
    cluster, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")

    result = manager.confirm(prepared.action_id, prepared.confirmation_token)
    node = next(item for item in cluster.snapshot().nodes if item.id == "gpu-node-03")

    assert result.recovered is True
    assert result.after.time_to_first_token_ms == 540
    assert result.after.queue_depth == 24
    assert node.status == "quarantined"


def test_confirmation_cannot_be_reused() -> None:
    _, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")
    manager.confirm(prepared.action_id, prepared.confirmation_token)

    with pytest.raises(RemediationError, match="already been used"):
        manager.confirm(prepared.action_id, prepared.confirmation_token)


def test_confirmation_is_bound_to_action() -> None:
    _, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")

    with pytest.raises(RemediationError, match="does not match"):
        manager.confirm("reduce_traffic", prepared.confirmation_token)


def test_state_change_invalidates_confirmation() -> None:
    cluster, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")
    cluster.reset()

    with pytest.raises(RemediationError, match="state changed"):
        manager.confirm(prepared.action_id, prepared.confirmation_token)


def test_exact_spoken_phrase_confirms_action() -> None:
    _, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")

    result = manager.confirm_by_phrase(
        prepared.action_id,
        prepared.confirmation_token,
        "Confirm drain and redistribute.",
    )

    assert result.recovered is True


def test_vague_spoken_confirmation_is_rejected_without_consuming_token() -> None:
    _, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")

    with pytest.raises(RemediationError, match="Say exactly"):
        manager.confirm_by_phrase(
            prepared.action_id,
            prepared.confirmation_token,
            "Yes, do it",
        )

    result = manager.confirm_by_phrase(
        prepared.action_id,
        prepared.confirmation_token,
        prepared.confirmation_phrase,
    )
    assert result.recovered is True


def test_cancelled_confirmation_cannot_execute() -> None:
    _, manager = failed_cluster()
    prepared = manager.prepare("drain_and_redistribute")
    manager.cancel(prepared.confirmation_token)

    with pytest.raises(RemediationError, match="already been used"):
        manager.confirm(prepared.action_id, prepared.confirmation_token)
