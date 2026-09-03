from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from .domain import (
    ExecutionResult,
    NodeStatus,
    PreparedAction,
    RemediationOption,
)
from .simulator import ClusterSimulator


class RemediationError(ValueError):
    pass


class RemediationManager:
    def __init__(self, cluster: ClusterSimulator) -> None:
        self.cluster = cluster
        self._pending: dict[str, dict[str, object]] = {}

    def options(self) -> list[RemediationOption]:
        state = self.cluster.snapshot()
        failed = next(
            (node for node in state.nodes if node.status == NodeStatus.FAILED),
            None,
        )
        hot = failed is not None and failed.temperature_c >= 90
        target = failed.id if failed else "the failed node"

        return [
            RemediationOption(
                action_id="drain_and_redistribute",
                title="Drain and redistribute workloads",
                description=f"Quarantine {target} and move capacity to healthy nodes.",
                risk="medium",
                reversible=True,
                recommended=failed is not None,
                available=failed is not None,
                blocked_reason=None if failed else "No failed node is present.",
            ),
            RemediationOption(
                action_id="restart_worker",
                title="Restart the inference worker",
                description=f"Restart serving on {target}.",
                risk="high",
                reversible=False,
                available=failed is not None and not hot,
                blocked_reason=(
                    f"Unsafe while {target} remains at {failed.temperature_c}°C."
                    if hot and failed
                    else (None if failed else "No failed node is present.")
                ),
            ),
            RemediationOption(
                action_id="reduce_traffic",
                title="Temporarily reduce incoming traffic",
                description="Lower admission rate to reduce queue pressure.",
                risk="low",
                reversible=True,
                available=state.inference.queue_depth > 50,
                blocked_reason=(
                    None
                    if state.inference.queue_depth > 50
                    else "Queue pressure is already within the safe range."
                ),
            ),
        ]

    def prepare(self, action_id: str) -> PreparedAction:
        option = next((item for item in self.options() if item.action_id == action_id), None)
        if option is None:
            raise RemediationError(f"Unknown remediation action: {action_id}")
        if not option.available:
            raise RemediationError(option.blocked_reason or "Action is unavailable")

        state = self.cluster.snapshot()
        token = token_urlsafe(18)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        phrase = f"confirm {action_id.replace('_', ' ')}"
        self._pending[token] = {
            "action_id": action_id,
            "expires_at": expires_at,
            "state_version": state.updated_at,
        }
        return PreparedAction(
            confirmation_token=token,
            action_id=action_id,
            confirmation_phrase=phrase,
            expires_at=expires_at,
        )

    def confirm(self, action_id: str, token: str) -> ExecutionResult:
        pending = self._pending.pop(token, None)
        if pending is None:
            raise RemediationError("Confirmation is invalid or has already been used")
        if pending["action_id"] != action_id:
            raise RemediationError("Confirmation does not match the requested action")
        if datetime.now(timezone.utc) > pending["expires_at"]:
            raise RemediationError("Confirmation has expired")

        current = self.cluster.snapshot()
        if current.updated_at != pending["state_version"]:
            raise RemediationError("Cluster state changed; prepare the action again")

        before = current.inference
        if action_id == "drain_and_redistribute":
            failed = next(
                (node for node in current.nodes if node.status == NodeStatus.FAILED),
                None,
            )
            if failed is None:
                raise RemediationError("No failed node is available to drain")
            after_state = self.cluster.drain_and_redistribute(failed.id)
        elif action_id == "reduce_traffic":
            after_state = self.cluster.reduce_traffic()
        else:
            raise RemediationError(f"Action is not executable: {action_id}")

        after = after_state.inference
        recovered = (
            after.time_to_first_token_ms < before.time_to_first_token_ms
            and after.queue_depth < before.queue_depth
            and after.error_rate_percent < before.error_rate_percent
        )
        return ExecutionResult(
            action_id=action_id,
            status="completed" if recovered else "completed_without_recovery",
            summary=(
                f"Recovery verified: TTFT {before.time_to_first_token_ms}→"
                f"{after.time_to_first_token_ms} ms, queue {before.queue_depth}→"
                f"{after.queue_depth}, error rate {before.error_rate_percent}→"
                f"{after.error_rate_percent}%."
            ),
            before=before,
            after=after,
            recovered=recovered,
        )

    def confirm_by_phrase(
        self,
        action_id: str,
        token: str,
        spoken_phrase: str,
    ) -> ExecutionResult:
        expected = f"confirm {action_id.replace('_', ' ')}"
        normalized = " ".join(spoken_phrase.lower().strip().rstrip(".!?").split())
        if normalized != expected:
            raise RemediationError(
                f'Confirmation phrase did not match. Say exactly: "{expected}"'
            )
        return self.confirm(action_id, token)

    def cancel(self, token: str) -> None:
        if self._pending.pop(token, None) is None:
            raise RemediationError("Pending confirmation is invalid or no longer active")
