#!/usr/bin/env python3
"""READ-ONLY verification that the live Supabase project matches what this repo expects (W7-12, D-01).

    python -X utf8 scripts/check_supabase.py

Point `DATABASE_URL` at Supabase's *session* pooler (port 5432 — see SETUP.md §5, "Supabase
production database"), then run this. It never prints the URL or any other secret, and it never
writes: the connection is forced into a read-only transaction mode before any query runs.

Checks (printed as a checklist, one line each):
  - `alembic_version` in the database equals this repo's migration head
  - Row Level Security is enabled on all 9 tables (the 8 app tables + `alembic_version`)
  - Supabase-only — reported as "skipped (not Supabase)" against a plain PostgreSQL such as the
    local Docker database or CI, which have neither an `auth` schema nor an `authenticated` role:
    - per-table RLS policy counts match migration 0002 exactly (derived from it, not duplicated)
    - no policy grants access to `anon`
    - `credentials` has no policies at all
    - `public.rls_auto_enable()`, if it exists, is not EXECUTE-able by `anon` or `authenticated`
    - Storage bucket `artifacts` exists and is private
    - the `supabase_realtime` publication contains exactly `execution_runs` and `execution_logs`

Exits 0 if every check that ran passed (skips don't count as failures), 1 otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

# Native Windows Python's console defaults to cp1252, which can't encode the checklist characters
# below (see SETUP.md's Windows notes / scripts/make_dist.py). Make this script self-sufficient
# rather than relying on the caller remembering `-X utf8`.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
OK, FAIL, SKIP = "✓", "✗", "-"  # check mark, ballot X, dash


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_head() -> str:
    """The repo's single migration head, read straight from db/migrations/versions (no DB needed)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "db" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one migration head in db/migrations/versions, found {heads}")
    return heads[0]


class Checklist:
    def __init__(self) -> None:
        self.failed = False

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = OK if ok else FAIL
        self.failed = self.failed or not ok
        print(f"{mark} {label}" + (f" — {detail}" if detail else ""))

    def skip(self, label: str, reason: str = "not Supabase") -> None:
        print(f"{SKIP} {label} — skipped ({reason})")


def _run_checks(conn, checklist: Checklist) -> None:
    rls_0002 = _load_module(ROOT / "db" / "migrations" / "versions" / "0002_row_level_security.py", "_c7_0002")
    app_tables: tuple[str, ...] = rls_0002.APP_TABLES
    rls_tables: tuple[str, ...] = rls_0002.RLS_TABLES
    expected_policies: dict[str, int] = dict.fromkeys(app_tables, 0)
    for table, _command, _predicate in rls_0002.POLICIES:
        expected_policies[table] += 1

    is_supabase = bool(
        conn.execute(
            "SELECT to_regprocedure('auth.uid()') IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')"
        ).fetchone()[0]
    )

    # -- alembic version --------------------------------------------------------------------
    import psycopg

    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except psycopg.errors.UndefinedTable:
        row = None
    db_version = row[0] if row else None
    repo_head = _repo_head()
    checklist.check(
        db_version == repo_head,
        "alembic_version is at the repo's migration head",
        f"db={db_version!r} repo={repo_head!r}" if db_version != repo_head else "",
    )

    # -- RLS enabled everywhere ---------------------------------------------------------------
    rows = conn.execute(
        "SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
    ).fetchall()
    rls_status = {name: on for name, on in rows if name in rls_tables}
    missing_rls = sorted(set(rls_tables) - {t for t, on in rls_status.items() if on})
    checklist.check(
        not missing_rls,
        f"Row Level Security is enabled on all {len(rls_tables)} tables",
        f"not enabled on: {', '.join(missing_rls)}" if missing_rls else "",
    )

    if not is_supabase:
        checklist.skip("RLS policy counts match migration 0002")
        checklist.skip("no policy grants access to anon")
        checklist.skip("credentials has no policies")
        checklist.skip("rls_auto_enable() is not executable by anon/authenticated")
        checklist.skip("Storage bucket 'artifacts' exists and is private")
        checklist.skip("supabase_realtime publication contains the expected tables")
        return

    # -- per-table policy counts (derived from 0002.POLICIES) ---------------------------------
    rows = conn.execute(
        "SELECT tablename, count(*) FROM pg_policies WHERE schemaname = 'public' GROUP BY tablename"
    ).fetchall()
    actual_policies = dict.fromkeys(app_tables, 0) | dict(rows)
    mismatches = [
        f"{t}: expected {expected_policies[t]}, got {actual_policies.get(t, 0)}"
        for t in app_tables
        if actual_policies.get(t, 0) != expected_policies[t]
    ]
    checklist.check(not mismatches, "RLS policy counts match migration 0002", "; ".join(mismatches))

    # -- no anon policies -----------------------------------------------------------------------
    anon_policies = conn.execute("SELECT count(*) FROM pg_policies WHERE 'anon' = ANY(roles)").fetchone()[0]
    checklist.check(
        anon_policies == 0, "no policy grants access to anon", f"{anon_policies} found" if anon_policies else ""
    )

    # -- credentials has no policies --------------------------------------------------------------
    credentials_policies = conn.execute(
        "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = 'credentials'"
    ).fetchone()[0]
    checklist.check(
        credentials_policies == 0,
        "credentials has no policies",
        f"{credentials_policies} found" if credentials_policies else "",
    )

    # -- rls_auto_enable() not executable by anon/authenticated -----------------------------------
    exists = conn.execute("SELECT to_regprocedure('public.rls_auto_enable()') IS NOT NULL").fetchone()[0]
    if not exists:
        checklist.skip("rls_auto_enable() is not executable by anon/authenticated", "function does not exist")
    else:
        grantees = [
            role
            for role in ("anon", "authenticated")
            if conn.execute(
                "SELECT has_function_privilege(%s, 'public.rls_auto_enable()', 'EXECUTE')", (role,)
            ).fetchone()[0]
        ]
        checklist.check(
            not grantees,
            "rls_auto_enable() is not executable by anon/authenticated",
            f"executable by: {', '.join(grantees)}" if grantees else "",
        )

    # -- Storage bucket 'artifacts' exists and is private --------------------------------------
    has_storage = conn.execute("SELECT to_regclass('storage.buckets') IS NOT NULL").fetchone()[0]
    if not has_storage:
        checklist.check(False, "Storage bucket 'artifacts' exists and is private", "storage.buckets not found")
    else:
        bucket = conn.execute("SELECT public FROM storage.buckets WHERE id = 'artifacts'").fetchone()
        if bucket is None:
            checklist.check(False, "Storage bucket 'artifacts' exists and is private", "bucket not found")
        else:
            checklist.check(
                bucket[0] is False,
                "Storage bucket 'artifacts' exists and is private",
                "bucket is public" if bucket[0] else "",
            )

    # -- Realtime publication contains the expected tables ---------------------------------------
    expected_realtime = {"execution_runs", "execution_logs"}
    has_publication = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')"
    ).fetchone()[0]
    if not has_publication:
        checklist.check(
            False, "supabase_realtime publication contains the expected tables", "publication does not exist"
        )
    else:
        actual_realtime = {
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_publication_tables "
                "WHERE pubname = 'supabase_realtime' AND schemaname = 'public'"
            ).fetchall()
        }
        checklist.check(
            actual_realtime == expected_realtime,
            "supabase_realtime publication contains the expected tables",
            f"expected {sorted(expected_realtime)}, got {sorted(actual_realtime)}"
            if actual_realtime != expected_realtime
            else "",
        )


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(f"{FAIL} DATABASE_URL is not set", file=sys.stderr)
        return 1

    try:
        import psycopg
    except ImportError:
        print(f"{FAIL} psycopg is not installed (pip install -c constraints.txt ./db)", file=sys.stderr)
        return 1

    try:
        conn = psycopg.connect(url, autocommit=True, connect_timeout=10)
    except psycopg.OperationalError as exc:
        # str(exc) may echo back connection parameters, but never the URL/password we were given.
        print(f"{FAIL} could not connect to DATABASE_URL: {exc}", file=sys.stderr)
        return 1

    checklist = Checklist()
    try:
        # Read-only for the rest of this script's lifetime — belt and braces on top of every
        # query below being a SELECT.
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        _run_checks(conn, checklist)
    finally:
        conn.close()

    return 1 if checklist.failed else 0


if __name__ == "__main__":
    sys.exit(main())
