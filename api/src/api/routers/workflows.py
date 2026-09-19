from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.catalog import CatalogSource
from api.deps import get_catalog, get_current_user, get_enqueuer, get_session, owned
from api.queue import Enqueuer
from api.schemas import (
    RunCreated,
    RunSummary,
    ValidationResult,
    WorkflowCreate,
    WorkflowOut,
    WorkflowSummary,
    WorkflowUpdate,
)
from api.services.run_reason import rejected_runs
from api.services.validation import validate_graph
from api.services.workflows import ordered_nodes, save_graph
from contracts.run import NodeStatus, RunStatus, WorkflowGraph
from db.models import ExecutionLog, ExecutionRun, User, Workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])
log = logging.getLogger(__name__)


def _load(session: Session, user: User, workflow_id: UUID) -> Workflow:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This workflow doesn't exist or isn't yours.")
    owned(user, workflow.user_id)
    return workflow


def _out(workflow: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=workflow.id,
        name=workflow.name,
        status=workflow.status,
        graph=WorkflowGraph.model_validate(workflow.graph_definition or {}),
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workflows = session.scalars(
        select(Workflow).where(Workflow.user_id == user.id).order_by(Workflow.updated_at.desc())
    ).all()
    latest = {}
    for wf in workflows:
        last = session.scalar(
            select(ExecutionRun)
            .where(ExecutionRun.workflow_id == wf.id)
            .order_by(ExecutionRun.created_at.desc())
            .limit(1)
        )
        if last is not None:
            latest[wf.id] = last
    # One query for every rejection on the page, rather than one per workflow. (The lookup of
    # each workflow's latest run above is still per-workflow, and predates this.)
    rejected = rejected_runs(session, [run.id for run in latest.values() if run.status == RunStatus.FAILED.value])

    summaries = []
    for wf in workflows:
        last = latest.get(wf.id)
        graph = WorkflowGraph.model_validate(wf.graph_definition or {})
        summaries.append(
            WorkflowSummary(
                id=wf.id,
                name=wf.name,
                status=wf.status,
                agent_types=[n.agent_type for n in ordered_nodes(graph)],
                updated_at=wf.updated_at,
                last_run=RunSummary(
                    id=last.id,
                    status=last.status,
                    created_at=last.created_at,
                    completed_at=last.completed_at,
                    reason="rejected" if last.id in rejected else None,
                )
                if last
                else None,
            )
        )
    return summaries


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    body: WorkflowCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    workflow = Workflow(user_id=user.id, name=body.name)
    session.add(workflow)
    save_graph(session, workflow, body.graph)
    session.commit()
    session.refresh(workflow)
    return _out(workflow)


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return _out(_load(session, user, workflow_id))


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    workflow = _load(session, user, workflow_id)
    if body.name is not None:
        workflow.name = body.name
    if body.graph is not None:
        save_graph(session, workflow, body.graph)
    session.commit()
    session.refresh(workflow)
    return _out(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    session.delete(_load(session, user, workflow_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/validate", response_model=ValidationResult)
def validate_workflow(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    catalog: CatalogSource = Depends(get_catalog),
):
    graph = WorkflowGraph.model_validate(_load(session, user, workflow_id).graph_definition or {})
    issues = validate_graph(graph, catalog.agents())
    return ValidationResult(valid=not any(i.severity == "error" for i in issues), issues=issues)


@router.post(
    "/{workflow_id}/run",
    response_model=RunCreated,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        422: {"model": ValidationResult, "description": "The workflow has validation errors"},
        503: {"description": "Job queue unavailable"},
    },
)
def run_workflow(
    workflow_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    catalog: CatalogSource = Depends(get_catalog),
    enqueuer: Enqueuer = Depends(get_enqueuer),
):
    """Enqueue a run and return immediately with 202 — the run has not finished (NFR-01)."""
    workflow = _load(session, user, workflow_id)
    graph = WorkflowGraph.model_validate(workflow.graph_definition or {})
    issues = validate_graph(graph, catalog.agents())
    if any(i.severity == "error" for i in issues):
        raise HTTPException(
            422,
            ValidationResult(valid=False, issues=issues).model_dump(mode="json"),
        )

    run = ExecutionRun(
        workflow_id=workflow.id,
        triggered_by=user.id,
        status=RunStatus.QUEUED.value,
        graph_snapshot=graph.model_dump(mode="json"),
        total_nodes=len(graph.nodes),
    )
    session.add(run)
    session.flush()
    for order, node in enumerate(ordered_nodes(graph)):
        session.add(
            ExecutionLog(
                run_id=run.id,
                workflow_id=workflow.id,
                node_id=node.id,
                agent_type=node.agent_type,
                position_order=order,
                status=NodeStatus.PENDING.value,
            )
        )
    session.commit()

    try:
        enqueuer.enqueue_run(run.id)
    except Exception:
        log.exception("failed to enqueue run %s", run.id)
        run.status = RunStatus.FAILED.value
        session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Couldn't start the run: the job queue is unavailable."
        ) from None
    return RunCreated(run_id=run.id, status=RunStatus.QUEUED)


@router.get("/{workflow_id}/runs", response_model=list[RunSummary])
def list_runs(workflow_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workflow = _load(session, user, workflow_id)
    runs = session.scalars(
        select(ExecutionRun)
        .where(ExecutionRun.workflow_id == workflow.id)
        .order_by(ExecutionRun.created_at.desc())
        .limit(50)
    ).all()
    rejected = rejected_runs(session, [r.id for r in runs if r.status == RunStatus.FAILED.value])
    return [
        RunSummary(
            id=r.id,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
            reason="rejected" if r.id in rejected else None,
        )
        for r in runs
    ]
