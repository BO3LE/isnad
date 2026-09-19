from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_session, owned
from api.schemas import OutputLink
from api.settings import ApiSettings, get_settings
from db.models import AgentOutput, ExecutionLog, User, Workflow

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _as_text(payload: dict[str, object] | None) -> str | None:
    """An agent's own output object, as words. Its string fields are the readable part of it."""
    if not payload:
        return None
    parts = [str(value) for value in payload.values() if isinstance(value, str) and value.strip()]
    return "\n\n".join(parts) if parts else None


@router.get("/{output_id}", response_model=OutputLink)
def download(
    output_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
):
    """Return a download URL — the API never streams files itself.

    Development serves files from STORAGE_ROOT at /files. TODO(W4): Supabase signed URLs in production.
    """
    row = session.execute(
        select(AgentOutput, Workflow.user_id)
        .join(ExecutionLog, ExecutionLog.id == AgentOutput.log_id)
        .join(Workflow, Workflow.id == ExecutionLog.workflow_id)
        .where(AgentOutput.id == output_id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This file doesn't exist or isn't yours.")
    output, owner = row
    owned(user, owner)
    if output.output_type == "url" and output.content:
        return OutputLink(id=output.id, url=output.content, expires_in=0)
    if output.output_type == "text":
        # Not every output is a file. An article is text, and the approval window has to be able to
        # show the words rather than offer a download that does not exist.
        written = output.content if output.content is not None else _as_text(output.content_json)
        if written is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "This output has nothing in it.")
        return OutputLink(id=output.id, text=written)
    if not output.storage_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This output has no file.")
    if settings.environment == "production":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Signed download URLs land in W4.")
    return OutputLink(
        id=output.id, url=f"{settings.public_files_url.rstrip('/')}/{output.storage_path}", expires_in=3600
    )
