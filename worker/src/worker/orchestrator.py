"""The orchestrator: topological order, execute, retry with backoff, park for approval, halt on failure.

Re-entrant: running it again on the same run skips nodes already `success`, so the same
code path resumes a run after an approval or after a worker restart.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from contracts.errors import AgentError
from contracts.graph import CycleError, ancestors, topological_order
from contracts.ports import Ports
from contracts.run import (
    MAX_RETRIES,
    REJECTED_BY_REVIEWER,
    TERMINAL_NODE_STATUSES,
    TERMINAL_RUN_STATUSES,
    ApprovalDecision,
    GraphNode,
    NodeStatus,
    RunStatus,
)
from worker.registry import Registry, UnknownAgentError
from worker.store import RunSnapshot, RunStore

log = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


def backoff_delay(attempt: int, jitter: float) -> float:
    """`2**attempt + random()` seconds — exactly as M2 §7.3.3 specifies."""
    return 2**attempt + jitter


class Orchestrator:
    def __init__(
        self,
        store: RunStore,
        registry: Registry,
        ports: Ports,
        *,
        max_retries: int = MAX_RETRIES,
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ):
        self.store = store
        self.registry = registry
        self.ports = ports
        self.max_retries = max_retries
        self._sleep = sleep
        self._jitter = jitter

    async def execute(self, run_id: UUID) -> RunStatus:
        snap = self.store.load(run_id)
        if snap.status in TERMINAL_RUN_STATUSES:
            return snap.status

        try:
            order = topological_order(snap.graph)
        except CycleError:
            return self._halt(snap, [], None, "The workflow contains a loop.")

        self.store.set_run_status(run_id, RunStatus.RUNNING)
        upstream_of = {n.id: ancestors(snap.graph, n.id) for n in order}
        outputs: dict[UUID, dict[str, Any]] = dict(snap.outputs)

        for index, node in enumerate(order):
            status = snap.node_status.get(node.id, NodeStatus.PENDING)
            if status == NodeStatus.SUCCESS:
                continue
            if status in TERMINAL_NODE_STATUSES:
                return self._finish_failed(snap, order[index:])

            if self.store.run_status(run_id) == RunStatus.CANCELLED:
                self._skip(snap, order[index:])
                return RunStatus.CANCELLED

            try:
                agent = self.registry.get(node.agent_type)
            except UnknownAgentError as exc:
                return self._halt(snap, order[index + 1 :], node, str(exc))

            if node.requires_approval or agent.manifest.requires_approval:
                decision = self.store.approval(run_id, node.id)
                if decision is None:
                    self.store.set_node_status(run_id, node.id, NodeStatus.AWAITING_APPROVAL)
                    self.store.set_run_status(run_id, RunStatus.AWAITING_APPROVAL)
                    return RunStatus.AWAITING_APPROVAL
                if decision == ApprovalDecision.REJECT:
                    return self._halt(snap, order[index + 1 :], node, REJECTED_BY_REVIEWER)

            # Run context: outputs of every upstream agent (not only the direct parent), oldest first,
            # so Publisher sees Writer's title as well as Video's file. Configuration wins.
            data: dict[str, Any] = {}
            for earlier in order[:index]:
                if earlier.id in upstream_of[node.id]:
                    data.update(outputs.get(earlier.id, {}))
            data.update(node.configuration)
            try:
                input_obj = agent.input_model.model_validate(data)
            except ValidationError as exc:
                return self._halt(
                    snap, order[index + 1 :], node, f"{agent.manifest.title} is missing input: {_describe(exc)}"
                )

            result = await self._run_with_retry(snap, node, agent, input_obj)
            if result is None:
                return self._finish_failed(snap, order[index + 1 :])
            outputs[node.id] = result

        self.store.set_run_status(run_id, RunStatus.SUCCEEDED)
        return RunStatus.SUCCEEDED

    async def _run_with_retry(
        self, snap: RunSnapshot, node: GraphNode, agent, input_obj: BaseModel
    ) -> dict[str, Any] | None:
        run_id = snap.run_id
        retry_count = snap.retry_counts.get(node.id, 0)
        self.store.set_node_status(run_id, node.id, NodeStatus.RUNNING, retry_count=retry_count)
        while True:
            try:
                produced = await agent.execute(input_obj, self.ports)
                payload = produced.model_dump() if isinstance(produced, BaseModel) else produced
                output = agent.output_model.model_validate(payload).model_dump(mode="json")
            except Exception as exc:
                message = _describe(exc)
                retryable = getattr(exc, "retryable", True) and not isinstance(exc, ValidationError)
                if not retryable or retry_count >= self.max_retries:
                    self.store.set_node_status(
                        run_id, node.id, NodeStatus.FAILED, retry_count=retry_count, error=message
                    )
                    log.warning("run %s node %s failed: %s", run_id, node.id, message)
                    return None
                retry_count += 1
                self.store.set_node_status(run_id, node.id, NodeStatus.RETRYING, retry_count=retry_count, error=message)
                await self._sleep(backoff_delay(retry_count, self._jitter()))
                self.store.set_node_status(run_id, node.id, NodeStatus.RUNNING, retry_count=retry_count)
                continue
            self.store.save_output(run_id, node.id, output)
            self.store.set_node_status(run_id, node.id, NodeStatus.SUCCESS, retry_count=retry_count)
            return output

    def _halt(self, snap: RunSnapshot, remaining: list[GraphNode], node: GraphNode | None, message: str) -> RunStatus:
        if node is not None:
            self.store.set_node_status(snap.run_id, node.id, NodeStatus.FAILED, error=message)
        return self._finish_failed(snap, remaining)

    def _finish_failed(self, snap: RunSnapshot, remaining: list[GraphNode]) -> RunStatus:
        self._skip(snap, remaining)
        self.store.set_run_status(snap.run_id, RunStatus.FAILED)
        return RunStatus.FAILED

    def _skip(self, snap: RunSnapshot, nodes: list[GraphNode]) -> None:
        for node in nodes:
            if snap.node_status.get(node.id, NodeStatus.PENDING) not in TERMINAL_NODE_STATUSES:
                self.store.set_node_status(snap.run_id, node.id, NodeStatus.SKIPPED)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, AgentError):
        return exc.message
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'} — {e['msg']}" for e in exc.errors()[:3])
    text = str(exc).strip() or exc.__class__.__name__
    return text.splitlines()[0][:500]
