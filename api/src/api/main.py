from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import __version__
from api.routers import agents, auth, health, outputs, runs, workflows
from api.settings import ApiSettings, get_settings


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="GP Platform API",
        version=__version__,
        description="Visual AI-agent workflow platform — C2 api. Contract agreed in GP-plan §5.3.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, workflows, runs, agents, outputs):
        app.include_router(module.router)

    if settings.environment != "production" and Path(settings.storage_root).is_dir():
        app.mount("/files", StaticFiles(directory=settings.storage_root), name="files")
    return app


app = create_app()
