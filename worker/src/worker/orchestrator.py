"""The orchestrator: topological order, execute, retry with backoff, park for approval, halt on failure.

Re-entrant: running it again on the same run skips nodes already `success`, so the same
code path resumes a run after an approval or after a worker restart.

A cancel is final. The API records it at once; the step running then is left to end, and the
orchestrator stops at the next point it checks — before each step and between retries — skips
what is left and closes the run. A cancel that lands after the last check is still kept: the store
never replaces a finished run's status, and the orchestrator returns the status the store reports.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from contracts.errors import AgentError, NonRetryableAgentError
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
from worker.run_storage import run_ports
from worker.store import RunSnapshot, RunStore

log = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
# Ports for one node. The default hands every node the same ports; in real mode the worker passes
# `worker.credentials.CredentialPorts`, which swaps in Google ports for a node that names an account.
PortsFor = Callable[[UUID, GraphNode], Awaitable[Ports]]


class _Cancelled(Exception):
    """The run was cancelled between two attempts of a step: no further attempt starts."""


class StepTimedOut(NonRetryableAgentError):
    """An attempt ran past the step deadline. Not retried: whatever held it would likely hold the next."""

    def __init__(self, title: str, seconds: float):
        minutes = seconds / 60
        took = f"{minutes:g} minutes" if minutes >= 1 else f"{seconds:g} seconds"
        super().__init__(f"{title} took longer than {took} and was stopped.", code="step_timeout")


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
        ports_for: PortsFor | None = None,
        step_timeout_s: float | None = None,
    ):
        self.store = store
        self.registry = registry
        self.ports = ports
        self._ports_for = ports_for
        # One attempt's deadline. Each adapter has its own timeouts; this is the backstop for a call
        # that has none, so a hung step can't hold the run until the broker hands the job out again.
        self.step_timeout_s = step_timeout_s
        self.max_retries = max_retries
        self._sleep = sleep
        self._jitter = jitter

    async def execute(self, run_id: UUID) -> RunStatus:
        snap = self.store.load(run_id)
        if snap.status == RunStatus.CANCELLED and any(
            snap.node_status.get(n.id, NodeStatus.PENDING) not in TERMINAL_NODE_STATUSES for n in snap.graph.nodes
        ):
            # Cancelled while a worker that has since been lost was running a step: no one will
            # finish that step now, so the run is closed here.
            return self._cancelled(snap, list(snap.graph.nodes))
        if snap.status in TERMINAL_RUN_STATUSES:
            return snap.status

        try:
            order = topological_order(snap.graph)
        except CycleError:
            return self._halt(snap, [], None, "The workflow contains a loop.")

        if self.store.set_run_status(run_id, RunStatus.RUNNING) == RunStatus.CANCELLED:
            return self._cancelled(snap, order)
        upstream_of = {n.id: ancestors(snap.graph, n.id) for n in order}
        outputs: dict[UUID, dict[str, Any]] = dict(snap.outputs)

        for index, node in enumerate(order):
            status = snap.node_status.get(node.id, NodeStatus.PENDING)
            if status == NodeStatus.SUCCESS:
                continue
            if status in TERMINAL_NODE_STATUSES:
                return self._finish_failed(snap, order[index:])

            if self.store.run_status(run_id) == RunStatus.CANCELLED:
                return self._cancelled(snap, order[index:])

            try:
                agent = self.registry.get(node.agent_type)
            except UnknownAgentError as exc:
                return self._halt(snap, order[index + 1 :], node, str(exc))

            # The manifest decides, not the graph: a distribute agent waits even if the saved
            # workflow says it needn't (see AgentManifest.needs_approval).
            if agent.manifest.needs_approval(node.requires_approval):
                decision = self.store.approval(run_id, node.id)
                if decision is None:
                    self.store.set_node_status(run_id, node.id, NodeStatus.AWAITING_APPROVAL)
                    if self.store.set_run_status(run_id, RunStatus.AWAITING_APPROVAL) == RunStatus.CANCELLED:
                        return self._cancelled(snap, order[index:])
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

            try:
                result = await self._run_with_retry(snap, node, agent, input_obj)
            except _Cancelled:
                return self._cancelled(snap, order[index + 1 :])
            if result is None:
                return self._finish_failed(snap, order[index + 1 :])
            outputs[node.id] = result

        return self.store.set_run_status(run_id, RunStatus.SUCCEEDED)

    async def _run_with_retry(
        self, snap: RunSnapshot, node: GraphNode, agent, input_obj: BaseModel
    ) -> dict[str, Any] | None:
        run_id = snap.run_id
        retry_count = snap.retry_counts.get(node.id, 0)
        self.store.set_node_status(run_id, node.id, NodeStatus.RUNNING, retry_count=retry_count)
        while True:
            try:
                # Resolved per attempt, inside the retry loop: a network blip while refreshing a
                # Google token is retried; an expired connection (not retryable) fails at once.
                base = await self._ports_for(run_id, node) if self._ports_for else self.ports
                ports = run_ports(base, snap.user_id, run_id)  # files land under {user_id}/{run_id}/
                produced = await self._attempt(agent, input_obj, ports)
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
                self._stop_if_cancelled(run_id, node, retry_count)  # landed during the attempt: don't wait
                await self._sleep(backoff_delay(retry_count, self._jitter()))
                self._stop_if_cancelled(run_id, node, retry_count)  # landed during the wait
                self.store.set_node_status(run_id, node.id, NodeStatus.RUNNING, retry_count=retry_count)
                continue
            self.store.complete_node(run_id, node.id, output, retry_count=retry_count)
            return output

    def _stop_if_cancelled(self, run_id: UUID, node: GraphNode, retry_count: int) -> None:
        """Between attempts. The step is skipped — the run is cancelled, not failed, so it doesn't count
        as a failed step — and keeps the log of the attempts it made."""
        if self.store.run_status(run_id) == RunStatus.CANCELLED:
            self.store.set_node_status(run_id, node.id, NodeStatus.SKIPPED, retry_count=retry_count)
            raise _Cancelled

    async def _attempt(self, agent, input_obj: BaseModel, ports: Ports) -> Any:
        deadline = asyncio.timeout(self.step_timeout_s)  # None: no deadline
        try:
            async with deadline:
                return await agent.execute(input_obj, ports)
        except TimeoutError as exc:
            if deadline.expired():  # ours ran out — not a TimeoutError an adapter raised (that is retried)
                raise StepTimedOut(agent.manifest.title, self.step_timeout_s) from exc
            raise

    def _halt(self, snap: RunSnapshot, remaining: list[GraphNode], node: GraphNode | None, message: str) -> RunStatus:
        if node is not None:
            self.store.set_node_status(snap.run_id, node.id, NodeStatus.FAILED, error=message)
        return self._finish_failed(snap, remaining)

    def _finish_failed(self, snap: RunSnapshot, remaining: list[GraphNode]) -> RunStatus:
        self._skip(snap, remaining)
        return self.store.set_run_status(snap.run_id, RunStatus.FAILED)  # stays cancelled if it was

    def _cancelled(self, snap: RunSnapshot, remaining: list[GraphNode]) -> RunStatus:
        """Skips what won't run now and closes the run, which records when it ended."""
        self._skip(snap, remaining)
        return self.store.set_run_status(snap.run_id, RunStatus.CANCELLED)

    def _skip(self, snap: RunSnapshot, nodes: list[GraphNode]) -> None:
        for node in nodes:
            if snap.node_status.get(node.id, NodeStatus.PENDING) not in TERMINAL_NODE_STATUSES:
                self.store.set_node_status(snap.run_id, node.id, NodeStatus.SKIPPED)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, AgentError):
        return exc.message
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'} — {e['msg']}" for e in exc.errors()[:3])
    # Anything else is a library's own message: it is shown to the person and logged, so whatever
    # in it could be a credential — a URL's query or user:password, a bearer token, key=value — goes.
    text = str(exc).strip() or exc.__class__.__name__
    return scrub(text.splitlines()[0])[:500]


_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@")
_URL_QUERY = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s?#'\"]*)\?[^\s#'\"]*")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]+")
_KEY_VALUE = re.compile(
    r"(?i)\b((?:access_|refresh_|id_)?token|api[_-]?key|apikey|secret|password|client_secret|authorization)"
    r"(['\"]?\s*[=:]\s*)(['\"]?)[^\s'\",;&]+"
)


def scrub(text: str) -> str:
    text = _URL_USERINFO.sub(r"\1[redacted]@", text)
    text = _URL_QUERY.sub(r"\1?[redacted]", text)
    text = _BEARER.sub(r"\1 [redacted]", text)
    return _KEY_VALUE.sub(r"\1\2\3[redacted]", text)
