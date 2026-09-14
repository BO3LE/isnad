from __future__ import annotations

from fastapi import APIRouter, Depends

from api.catalog import CatalogSource
from api.deps import get_catalog, get_current_user
from contracts.manifest import AgentManifest

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(get_current_user)])


@router.get("/catalog", response_model=list[AgentManifest])
def catalog(source: CatalogSource = Depends(get_catalog)):
    """Every installed agent with the JSON Schema of its configuration. Drives the palette and the
    configuration drawer, so a new agent appears with a working form and no frontend change (NFR-04).
    Empty until a worker has started."""
    return source.agents() or []
