from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.catalog import CatalogSource
from api.deps import get_catalog, get_current_user, get_session, owned
from api.schemas import OutputLink
from api.settings import ApiSettings, get_settings
from db.models import AgentOutput, ExecutionLog, User, Workflow

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _render(value: object) -> str | None:
    """One value from an agent's output object, as a person would read it."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        rendered = [item for item in (_render(v) for v in value) if item]
        return "\n".join(f"- {item}" for item in rendered) or None
    if isinstance(value, dict):
        rendered = [f"{k}: {item}" for k, v in value.items() if (item := _render(v))]
        return " · ".join(rendered) or None
    return None


def _as_text(payload: dict[str, object] | None, titles: dict[str, str] | None = None) -> str | None:
    """An agent's own output object, as words.

    Written generically on purpose: an agent publishes whatever shape it likes, and the approval
    window has to read it without the platform knowing which agent wrote it (AT-12). Each field is
    named with the agent's own word for it where the catalog has one — "article", not the
    mechanical "article md" — so what a person reads is what the agent calls its own work.
    """
    if not payload:
        return None
    blocks: list[str] = []
    for key, value in payload.items():
        rendered = _render(value)
        if rendered is None:
            continue
        label = (titles or {}).get(key) or key.replace("_", " ")
        block = "\n" in rendered or rendered.startswith("- ")
        blocks.append(f"{label}:\n{rendered}" if block else f"{label}: {rendered}")
    return "\n\n".join(blocks) or None


@router.get("/{output_id}", response_model=OutputLink)
def download(
    output_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
    catalog: CatalogSource = Depends(get_catalog),
):
    """Return a download URL — the API never streams files itself.

    Development serves files from STORAGE_ROOT at /files. TODO(W4): Supabase signed URLs in production.
    """
    row = session.execute(
        select(AgentOutput, Workflow.user_id, ExecutionLog.agent_type)
        .join(ExecutionLog, ExecutionLog.id == AgentOutput.log_id)
        .join(Workflow, Workflow.id == ExecutionLog.workflow_id)
        .where(AgentOutput.id == output_id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This file doesn't exist or isn't yours.")
    output, owner, agent_type = row
    owned(user, owner)
    if output.output_type == "url" and output.content:
        return OutputLink(id=output.id, url=output.content, expires_in=0)
    if output.output_type == "text":
        # Not every output is a file. An article is text, and the approval window has to be able to
        # show the words rather than offer a download that does not exist.
        manifest = next((m for m in (catalog.agents() or []) if m.name == agent_type), None)
        titles = {o.name: o.title for o in manifest.outputs} if manifest else {}
        written = output.content if output.content is not None else _as_text(output.content_json, titles)
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
