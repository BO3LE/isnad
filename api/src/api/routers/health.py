from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from api import __version__
from api.catalog import CatalogSource
from api.deps import get_catalog, get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness. Cheap, no dependencies."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
def ready(
    response: Response, session: Session = Depends(get_session), catalog: CatalogSource = Depends(get_catalog)
) -> dict:
    """Readiness: database reachable, and whether a worker has published the agent catalog."""
    checks: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    agents = catalog.agents()
    checks["worker_catalog"] = f"{len(agents)} agents" if agents is not None else "not published"
    if checks["database"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if checks["database"] == "ok" else "degraded", "checks": checks}
