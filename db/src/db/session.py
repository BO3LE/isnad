"""C7 · db/session.py

Two engine factories, because the two callers have different connection lifetimes:

- `make_engine` / `make_session_factory` — SYNC. Used by Celery workers (C3) and Alembic.
  Celery tasks are sync functions; a sync engine + sync Session is simplest and avoids
  running an event loop inside a worker process.

- `make_async_engine` / `make_async_session_factory` — ASYNC. Used by FastAPI (C2).
  FastAPI's request lifecycle is async; blocking on a sync DB call inside an `async def`
  endpoint ties up the event loop, so the API gets its own async engine.

Both point at the SAME Postgres database, just through different Supabase pooler
endpoints (see the pool-mode note below) — that's a deployment/URL concern, not a
schema concern, so it lives here in `db`, not in `api` or `worker`.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker


def normalise_url(url: str, *, async_driver: bool = False) -> str:
    """Accept the `postgresql://` URLs Supabase and Docker give us.

    async_driver=False -> postgresql+psycopg://   (psycopg 3, sync)  — worker, Alembic
    async_driver=True  -> postgresql+psycopg://   (psycopg 3, async) — same driver string;
                            psycopg 3 speaks both sync and async depending on whether you
                            call create_engine or create_async_engine against it.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


# ---------------------------------------------------------------------------
# SYNC — Celery workers (C3), Alembic migrations
# ---------------------------------------------------------------------------
#
# Supabase note: point this at the *session* pooler (port 5432) or the direct
# connection, NOT the transaction pooler. Workers hold a connection for the
# duration of a task (can be seconds to minutes for video/publish agents) and
# Alembic needs a stable session for DDL — both are a poor fit for a
# transaction-mode pooler, which recycles the underlying connection between
# transactions and will silently break session-scoped state.


def make_engine(url: str, **kwargs: object) -> Engine:
    kwargs.setdefault("pool_pre_ping", True)
    # pool_size / max_overflow only make sense for QueuePool (the default). A caller that
    # passes poolclass=NullPool (Alembic's env.py does, for the one-shot migration
    # connection) must NOT get these — NullPool doesn't accept sizing kwargs at all and
    # create_engine() raises TypeError if they're present alongside it.
    if "poolclass" not in kwargs:
        kwargs.setdefault("pool_size", 5)
        kwargs.setdefault("max_overflow", 5)
        kwargs.setdefault("pool_recycle", 1800)  # recycle before Supabase's idle-connection timeout
    return create_engine(normalise_url(url), **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# ASYNC — FastAPI (C2)
# ---------------------------------------------------------------------------
#
# Supabase note: point this at the *transaction* pooler (port 6543) instead.
# The API opens/closes a connection per request, potentially from many
# concurrent/serverless instances — exactly what pgbouncer's transaction mode
# is for. Two things that matter with a transaction pooler:
#   1. Keep the SQLAlchemy-side pool SMALL (pgbouncer is doing the real pooling;
#      stacking a large app-side pool on top just exhausts pgbouncer's own limit).
#   2. Disable server-side prepared statement caching — pgbouncer transaction
#      mode reassigns the physical connection between transactions, so a
#      statement prepared on one physical connection can be replayed against a
#      different one. psycopg 3 doesn't opt into server-side prepares by
#      default, but we pin it off explicitly so this doesn't silently change
#      if that default ever changes.


def make_async_engine(url: str, **kwargs: object) -> AsyncEngine:
    connect_args = dict(kwargs.pop("connect_args", {}) or {})
    connect_args.setdefault("prepare_threshold", None)  # never use server-side prepares (pgbouncer txn mode)
    kwargs.setdefault("pool_pre_ping", True)
    if "poolclass" not in kwargs:
        kwargs.setdefault("pool_size", 5)
        kwargs.setdefault("max_overflow", 10)
        kwargs.setdefault("pool_recycle", 1800)
    return create_async_engine(normalise_url(url, async_driver=True), connect_args=connect_args, **kwargs)


def make_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)
