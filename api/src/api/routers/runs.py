from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_enqueuer, get_session, owned
from api.queue import Enqueuer
from api.schemas import ApprovalRequest, RunCreated
from contracts.run import TERMINAL_RUN_STATUSES, LogEntry, NodeState, NodeStatus, RunState, RunStatus
from db.models import Approval, ExecutionLog, ExecutionRun, User, Workflow

router = APIRouter(prefix="/runs", tags=["runs"])


def _load(session: Session, user: User, run_id: UUID) -> ExecutionRun:
    run = session.get(ExecutionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This run doesn't exist or isn't yours.")
    owned(user, session.scalar(select(Workflow.user_id).where(Workflow.id == run.workflow_id)))
    return run


def _logs(session: Session, run_id: UUID) -> list[ExecutionLog]:
    return list(
        session.scalars(
            select(ExecutionLog).where(ExecutionLog.run_id == run_id).order_by(ExecutionLog.position_order)
        ).all()
    )


def _node_state(row: ExecutionLog) -> NodeState:
    return NodeState(
        node_id=row.node_id,
        agent_type=row.agent_type,
        status=row.status,
        retry_count=row.retry_count,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
        error_message=row.error_message,
    )


def _state(session: Session, run: ExecutionRun) -> RunState:
    return RunState(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        total_nodes=run.total_nodes,
        failed_nodes=run.failed_nodes,
        nodes=[_node_state(row) for row in _logs(session, run.id)],
    )


@router.get("/{run_id}", response_model=RunState)
def get_run(run_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return _state(session, _load(session, user, run_id))


@router.get("/{run_id}/logs", response_model=list[LogEntry])
def get_logs(run_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    run = _load(session, user, run_id)
    return [LogEntry(id=row.id, run_id=run.id, **_node_state(row).model_dump()) for row in _logs(session, run.id)]


@router.post("/{run_id}/nodes/{node_id}/approve", response_model=RunCreated, status_code=status.HTTP_202_ACCEPTED)
def decide(
    run_id: UUID,
    node_id: UUID,
    body: ApprovalRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    enqueuer: Enqueuer = Depends(get_enqueuer),
):
    """UC-04: record the decision, then hand the run back to the worker, which resumes or halts it."""
    run = _load(session, user, run_id)
    row = session.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run.id, ExecutionLog.node_id == node_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This step isn't part of the run.")
    if row.status != NodeStatus.AWAITING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "This step isn't waiting for approval.")
    if body.decision == "reject" and not (body.note or "").strip():
        raise HTTPException(422, "Add a note to reject — it's kept with the run.")
    session.add(Approval(log_id=row.id, decision=body.decision.value, decided_by=user.id, note=body.note))
    run.status = RunStatus.QUEUED.value
    session.commit()
    enqueuer.enqueue_run(run.id)
    return RunCreated(run_id=run.id, status=RunStatus.QUEUED)


@router.post("/{run_id}/cancel", response_model=RunState, status_code=status.HTTP_202_ACCEPTED)
def cancel(run_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    run = _load(session, user, run_id)
    if RunStatus(run.status) in TERMINAL_RUN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This run has already finished.")
    run.status = RunStatus.CANCELLED.value
    # Steps that haven't started are skipped now; a step already running finishes and the worker skips the rest.
    session.execute(
        update(ExecutionLog)
        .where(ExecutionLog.run_id == run.id, ExecutionLog.status.in_(["pending", "awaiting_approval"]))
        .values(status=NodeStatus.SKIPPED.value)
    )
    session.commit()
    session.refresh(run)
    return _state(session, run)
