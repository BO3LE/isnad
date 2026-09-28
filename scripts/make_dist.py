#!/usr/bin/env python3
"""Build the CD/DVD distribution for GP-plan W12 (C7).

    python3 scripts/make_dist.py [--out DIR]

Produces <out>/isnad-cd/ and <out>/isnad-cd.zip containing:
  source/          complete source code, via `git archive HEAD` (tracked files only — no
                    .env, node_modules, .venv, .git, build junk, or secrets can get in)
  SETUP.md         copied from the repository root, unmodified
  README-CD.md     explains the disc layout and how to run it
  TOOLS.md         every free/open-source tool and library used, with version and licence,
                    derived from pyproject.toml / constraints.txt / package.json / the
                    docker images in the compose files
  report/          placeholder for the M3 report PDF (not written yet)

Refuses to run if:
  - the working tree is dirty (`git status --porcelain` is non-empty) — the disc must be
    built from a real commit, not a mix of committed and uncommitted work
  - any tracked file looks like a secret (.env*, *.pem, *.key, id_rsa*, credentials.json, ...)

Standard library only, so it runs anywhere `python3` does.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CD_NAME = "isnad-cd"

# Native Windows Python's console defaults to cp1252, which can't encode the ✓ and — characters
# below — the same UnicodeEncodeError documented in SETUP.md's Windows notes for smoke_test.py.
# Make this script self-sufficient (no -X utf8 required) rather than relying on the caller.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ---------------------------------------------------------------- secret guard

SECRET_PATTERNS = [
    re.compile(r"(^|/)\.env(\.[^.]+)?$"),  # .env, .env.production, ... (but not .env.example)
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"(^|/)id_rsa"),
    re.compile(r"(^|/)id_ed25519"),
    re.compile(r"(^|/)credentials\.json$"),
    re.compile(r"(^|/)\.netrc$"),
    re.compile(r"\.p12$"),
    re.compile(r"\.pfx$"),
    re.compile(r"(^|/)secrets?\.ya?ml$"),
]
SECRET_ALLOW = {".env.example"}


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True).stdout


def check_clean_tree() -> None:
    status = run(["git", "status", "--porcelain"])
    if status.strip():
        print("refusing to build: the working tree is dirty —\n" + status, file=sys.stderr)
        print("commit or stash first, then rerun.", file=sys.stderr)
        raise SystemExit(1)


def tracked_files() -> list[str]:
    return [f for f in run(["git", "ls-files"]).splitlines() if f]


def check_no_secrets(files: list[str]) -> None:
    hits = []
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if name in SECRET_ALLOW:
            continue
        if any(p.search(f) for p in SECRET_PATTERNS):
            hits.append(f)
    if hits:
        print("refusing to build: secret-shaped file(s) are tracked by git:", file=sys.stderr)
        for h in hits:
            print(f"    {h}", file=sys.stderr)
        print("remove them from the repository (git rm --cached) before building the disc.", file=sys.stderr)
        raise SystemExit(1)


# ---------------------------------------------------------------- source export


def export_source(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest.parent / "_source.zip"
    subprocess.run(["git", "archive", "--format=zip", "-o", str(tmp_zip), "HEAD"], cwd=ROOT, check=True)
    with zipfile.ZipFile(tmp_zip) as zf:
        zf.extractall(dest)
    tmp_zip.unlink()


# ---------------------------------------------------------------- TOOLS.md

# Curated, best-effort SPDX licence for each package this repository depends on directly.
# Versions are read from the repo at build time (constraints.txt / package-lock.json), so they
# stay accurate; the licence text here should be re-checked if a dependency changes.
PY_LICENSES: dict[str, str] = {
    "fastapi": "MIT",
    "uvicorn": "BSD-3-Clause",
    "pydantic": "MIT",
    "pydantic-settings": "MIT",
    "PyJWT": "MIT",
    "celery": "BSD-3-Clause",
    "redis": "MIT",
    "httpx": "BSD-3-Clause",
    "sqlalchemy": "MIT",
    "alembic": "MIT",
    "psycopg": "LGPL-3.0-or-later",
    "cryptography": "Apache-2.0 OR BSD-3-Clause",
    "gTTS": "MIT",
    "weasyprint": "BSD-3-Clause",
    "markdown": "BSD-3-Clause",
    "python-docx": "MIT",
    "openai": "Apache-2.0",
    "google-api-python-client": "Apache-2.0",
    "google-auth": "Apache-2.0",
    "google-auth-oauthlib": "Apache-2.0",
    "google-auth-httplib2": "Apache-2.0",
    "pytest": "MIT",
    "pytest-asyncio": "Apache-2.0",
    "ruff": "MIT",
    "pre-commit": "MIT",
    "import-linter": "BSD-2-Clause",
    "watchfiles": "MIT",
    "psutil": "BSD-3-Clause",
}

JS_LICENSES: dict[str, str] = {
    "react": "MIT",
    "react-dom": "MIT",
    "react-router-dom": "MIT",
    "reactflow": "MIT",
    "@tanstack/react-query": "MIT",
    "zustand": "MIT",
    "@supabase/supabase-js": "MIT",
    "lucide-react": "ISC",
    "@fontsource/geist-mono": "MIT (package) / SIL OFL 1.1 (bundled font)",
    "@fontsource/geist-sans": "MIT (package) / SIL OFL 1.1 (bundled font)",
    "@fontsource/instrument-serif": "MIT (package) / SIL OFL 1.1 (bundled font)",
    "vite": "MIT",
    "vitest": "MIT",
    "typescript": "Apache-2.0",
    "eslint": "MIT",
    "@eslint/js": "MIT",
    "typescript-eslint": "MIT",
    "eslint-plugin-react-hooks": "MIT",
    "eslint-plugin-react-refresh": "MIT",
    "globals": "MIT",
    "@playwright/test": "Apache-2.0",
    "tailwindcss": "MIT",
    "postcss": "MIT",
    "autoprefixer": "MIT",
    "openapi-typescript": "MIT",
    "jsdom": "MIT",
    "@testing-library/react": "MIT",
    "@testing-library/jest-dom": "MIT",
    "@testing-library/user-event": "MIT",
    "@vitejs/plugin-react": "MIT",
    "@types/node": "MIT",
    "@types/react": "MIT",
    "@types/react-dom": "MIT",
}

# name -> (version as resolved on this repo's compose files, licence, note)
INFRA_TOOLS: list[tuple[str, str, str, str]] = [
    ("Git", "any recent (tested: 2.55)", "GPL-2.0-only", "version control"),
    ("Docker Engine / CLI", "24+ (tested: 29.7.2)", "Apache-2.0", "runs the whole stack"),
    ("Docker Compose", "v2 (tested: v5.5.0)", "Apache-2.0", "orchestrates the compose files"),
    (
        "Docker Desktop",
        "24+ (tested: bundled with Engine 29.7.2)",
        "Free for personal use, education and small business (proprietary; not open-source)",
        "convenience GUI wrapper around Docker Engine — Docker Engine + Compose alone are enough on Linux",
    ),
    ("Python", "3.11+ (.python-version: 3.11)", "PSF-2.0", "api, worker, agents, adapters, exporters, db, scripts"),
    ("Node.js", "20 LTS (.nvmrc: 20)", "MIT", "frontend build and dev server"),
    ("PostgreSQL", "15 (docker-compose.yml: postgres:15; resolved: 15.19)", "PostgreSQL License", "database (development; Supabase-managed Postgres in production)"),
    (
        "Redis",
        "7 (docker-compose.yml: redis:7-alpine; resolved: 7.4.11)",
        "RSALv2 / SSPLv1 dual license (source-available, NOT OSI open source since Redis 7.4 — "
        "see note below)",
        "Celery broker + result backend",
    ),
    ("nginx", "1.27 (docker-compose.prod.yml: nginx:1.27-alpine; resolved: 1.27.5)", "BSD-2-Clause", "serves the built frontend in production"),
    (
        "FFmpeg",
        "Debian package (worker/Dockerfile: apt-get install ffmpeg; resolved: 7.1.5, Debian 13)",
        "GPL-2.0-or-later (Debian's default build enables GPL components, e.g. libx264)",
        "renders the Video agent's MP4 output",
    ),
]

REDIS_LICENSE_NOTE = (
    "**Note on Redis's licence.** `docker-compose.yml` pins the floating tag `redis:7-alpine`. As "
    "of Redis 7.4 (March 2024), Redis Ltd. relicensed Redis under the Redis Source Available "
    "License v2 / Server Side Public License v1 — a source-available licence, not an OSI-approved "
    "open-source one. Resolving that tag on 2026-09-28 gave 7.4.11 (post-relicense). If the report "
    "must claim every tool is strictly open-source, either pin `redis:7.2-alpine` (last BSD-3-Clause "
    "release) or switch to a BSD-licensed fork such as Valkey (`valkey/valkey`). This is flagged "
    "here, not fixed, because it changes the pinned Docker image and is a C7/infra decision."
)


def read_constraints() -> dict[str, str]:
    versions: dict[str, str] = {}
    text = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        versions[name.strip().lower()] = version.strip()
    return versions


def component_dependencies() -> dict[str, list[str]]:
    """Direct third-party dependencies declared by each component's pyproject.toml, plus
    requirements-dev.txt for dev tooling. Internal gp-* packages are excluded (not third-party)."""
    deps: dict[str, list[str]] = {}
    for pyproject in sorted(ROOT.glob("*/pyproject.toml")):
        component = pyproject.parent.name
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        names: set[str] = set()
        for dep in project.get("dependencies", []):
            names.add(_dep_name(dep))
        for group in project.get("optional-dependencies", {}).values():
            for dep in group:
                names.add(_dep_name(dep))
        names = {n for n in names if n and not n.startswith("gp-")}
        if names:
            deps[component] = sorted(names)

    dev_names = []
    for line in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            dev_names.append(_dep_name(line))
    deps["dev tooling (requirements-dev.txt)"] = sorted(dev_names)
    return deps


def _dep_name(spec: str) -> str:
    # "fastapi>=0.115,<1" / "PyJWT[crypto]>=2.9" / "gp-adapters[all]" -> the bare package name
    name = re.split(r"[\[<>=!~; ]", spec.strip(), maxsplit=1)[0]
    return name.strip()


def read_package_lock_versions() -> dict[str, str]:
    lock_path = ROOT / "frontend" / "package-lock.json"
    if not lock_path.is_file():
        return {}
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for path, meta in data.get("packages", {}).items():
        if not path.startswith("node_modules/"):
            continue
        name = path[len("node_modules/") :]
        if "/node_modules/" in name:
            continue  # nested/transitive copy — keep the top-level resolution
        version = meta.get("version")
        if version:
            versions[name] = version
    return versions


def frontend_dependencies() -> dict[str, dict[str, str]]:
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock_versions = read_package_lock_versions()
    out: dict[str, dict[str, str]] = {}
    for group in ("dependencies", "devDependencies"):
        for name, spec in pkg.get(group, {}).items():
            out[name] = {"version": lock_versions.get(name, spec), "group": group}
    return out


def build_tools_md(dest: Path, commit: str) -> None:
    constraints = read_constraints()
    py_deps = component_dependencies()

    lines: list[str] = []
    lines.append("# Tools and libraries used")
    lines.append("")
    lines.append(
        f"Generated by `scripts/make_dist.py` from commit `{commit}` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Every tool below is free to use; "
        "licences are noted per entry (`OSI open-source` unless stated otherwise). Versions for "
        "Python and JavaScript packages are the exact pins in `constraints.txt` / "
        "`frontend/package-lock.json`; versions for infrastructure (Docker images, language "
        "runtimes) are what the compose files request, with the version actually resolved at the "
        "time this file was generated noted alongside (those tags float, so a later build can "
        "resolve a newer patch release)."
    )
    lines.append("")
    lines.append("## Infrastructure")
    lines.append("")
    lines.append("| Tool | Version | Licence | Used for |")
    lines.append("|---|---|---|---|")
    for name, version, licence, used_for in INFRA_TOOLS:
        lines.append(f"| {name} | {version} | {licence} | {used_for} |")
    lines.append("")
    lines.append(REDIS_LICENSE_NOTE)
    lines.append("")

    lines.append("## Python libraries (direct dependencies, by component)")
    lines.append("")
    lines.append(
        "Internal `gp-*` packages (this repository's own components — contracts, api, worker, "
        "agents, adapters, exporters, db) are omitted; only third-party dependencies are listed. "
        "Every transitive dependency actually installed is pinned in "
        "[`constraints.txt`](../constraints.txt)."
    )
    lines.append("")
    for component in sorted(py_deps):
        names = py_deps[component]
        if not names:
            continue
        lines.append(f"### {component}")
        lines.append("")
        lines.append("| Package | Version | Licence |")
        lines.append("|---|---|---|")
        for name in names:
            version = constraints.get(name.lower(), "— (not in constraints.txt)")
            licence = PY_LICENSES.get(name, "see project licence (not curated)")
            lines.append(f"| {name} | {version} | {licence} |")
        lines.append("")

    lines.append("## Frontend (JavaScript/TypeScript) libraries")
    lines.append("")
    fe = frontend_dependencies()
    lines.append("| Package | Version | Licence |")
    lines.append("|---|---|---|")
    for name in sorted(fe):
        info = fe[name]
        licence = JS_LICENSES.get(name, "see project licence (not curated)")
        lines.append(f"| {name} | {info['version']} | {licence} |")
    lines.append("")

    lines.append("## Fonts")
    lines.append("")
    lines.append(
        "Geist Sans, Geist Mono and Instrument Serif are bundled via the `@fontsource/*` npm "
        "packages above (SIL Open Font License 1.1 for the font files themselves)."
    )
    lines.append("")

    (dest / "TOOLS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- README-CD.md / report/


def build_readme_cd(dest: Path, commit: str) -> None:
    text = f"""# Isnad — CD/DVD contents

This disc image was built by `scripts/make_dist.py` from commit `{commit}` on
{datetime.now(timezone.utc).strftime('%Y-%m-%d')} (GP-plan W12, C7).

## Layout

| Path | What |
|---|---|
| `source/` | Complete source code (`git archive` of the commit above — every tracked file, nothing else: no `.env`, no `node_modules`, no `.venv`, no build output). |
| `SETUP.md` | The environment and database how-to. Follow this to run the platform from `source/`. |
| `TOOLS.md` | Every free/open-source tool and library used, with version and licence. |
| `report/` | Where the M3 report PDF goes — see `report/README.md`. |
| `README-CD.md` | This file. |

## How to run it

1. Copy `source/` to a writable location on your machine (the disc itself is read-only).
2. Open a terminal there and follow `SETUP.md`, starting at "Run the whole stack (Docker)":

   ```bash
   cp .env.example .env
   docker compose up --build
   ```
3. Open http://localhost:5173 and sign in as `demo@gp.local` (development sign-in, no password).
4. `python3 scripts/smoke_test.py` proves the whole stack works end to end (three seeded
   template workflows, run against fake external services — no API keys or spend needed).

`source/` has no `.git` directory (this is a source snapshot, not a clone) — if you need the
commit history, see the project's repository instead.

## Requirements

Docker Desktop (or Docker Engine + Compose v2) is the only hard requirement to run the platform.
See `SETUP.md` §1 for everything else (only needed for local, non-Docker development) and
`TOOLS.md` for the full list of what's used, with licences.
"""
    (dest / "README-CD.md").write_text(text, encoding="utf-8")


def build_report_placeholder(dest: Path) -> None:
    report_dir = dest / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    text = """# Report

Put the M3 report PDF here as `isnad-report.pdf` before burning/writing the final disc.

This folder is a placeholder: the report is not written yet (GP-plan Milestone 3, due 5 Dec 2026).
`scripts/make_dist.py` does not generate it — it only reserves the place for it so the CD/DVD
layout described in `README-CD.md` is stable from now on.
"""
    (report_dir / "README.md").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- zip + main


def zip_dir(src_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(Path(src_dir.name) / path.relative_to(src_dir)))


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "dist"), help="output directory (default: dist/)")
    args = parser.parse_args()

    check_clean_tree()
    files = tracked_files()
    check_no_secrets(files)

    commit = run(["git", "rev-parse", "--short", "HEAD"]).strip()

    out_dir = Path(args.out).resolve()
    cd_dir = out_dir / CD_NAME
    if cd_dir.exists():
        shutil.rmtree(cd_dir)
    cd_dir.mkdir(parents=True)

    print(f"exporting source (git archive HEAD @ {commit})...")
    export_source(cd_dir / "source")

    print("copying SETUP.md...")
    shutil.copyfile(ROOT / "SETUP.md", cd_dir / "SETUP.md")

    print("writing TOOLS.md...")
    build_tools_md(cd_dir, commit)

    print("writing README-CD.md...")
    build_readme_cd(cd_dir, commit)

    print("creating report/ placeholder...")
    build_report_placeholder(cd_dir)

    zip_path = out_dir / f"{CD_NAME}.zip"
    print(f"zipping to {zip_path}...")
    zip_dir(cd_dir, zip_path)

    # Verify: no secret-shaped file made it into the output, by name.
    offenders = [
        p
        for p in cd_dir.rglob("*")
        if p.is_file()
        and p.name not in SECRET_ALLOW
        and any(pat.search(p.name) for pat in SECRET_PATTERNS)
    ]
    if offenders:
        print("BUILD PRODUCED A SECRET-SHAPED FILE — this should be unreachable:", file=sys.stderr)
        for o in offenders:
            print(f"    {o}", file=sys.stderr)
        raise SystemExit(1)

    print()
    print(f"✓ {cd_dir} ({human(dir_size(cd_dir))})")
    print(f"✓ {zip_path} ({human(zip_path.stat().st_size)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
