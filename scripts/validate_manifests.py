#!/usr/bin/env python3
"""CI check: every agent folder is shaped the same way (GP-plan Part 2 · "Agent shape").

For each `agents/<name>/`:
- pyproject.toml declares exactly one `gp.agents` entry point, named <name>
- src/agents/<name>/manifest.json exists and validates as contracts.manifest.AgentManifest
- the manifest's `name` equals the folder name
- input_type / output_type name real models in contracts.agent_io
- a tests/ folder exists
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError

from contracts import agent_io
from contracts.manifest import AgentManifest

ROOT = Path(__file__).resolve().parents[1]


def check(folder: Path) -> list[str]:
    name = folder.name
    problems: list[str] = []
    pyproject = folder / "pyproject.toml"
    if not pyproject.is_file():
        return [f"{name}: missing pyproject.toml"]
    eps = tomllib.loads(pyproject.read_text()).get("project", {}).get("entry-points", {}).get("gp.agents", {})
    if list(eps) != [name]:
        problems.append(
            f"{name}: pyproject must declare exactly one gp.agents entry point named {name!r} (found {list(eps)})"
        )

    manifest_path = folder / "src" / "agents" / name / "manifest.json"
    if not manifest_path.is_file():
        return [*problems, f"{name}: missing src/agents/{name}/manifest.json"]
    try:
        manifest = AgentManifest.model_validate(json.loads(manifest_path.read_text()))
    except (ValidationError, json.JSONDecodeError) as exc:
        return [*problems, f"{name}: invalid manifest.json — {exc}"]
    if manifest.name != name:
        problems.append(f"{name}: manifest name {manifest.name!r} does not match folder")
    for field in ("input_type", "output_type"):
        model = getattr(manifest, field)
        if not hasattr(agent_io, model):
            problems.append(f"{name}: {field} {model!r} is not a model in contracts.agent_io")
    if not (folder / "tests").is_dir():
        problems.append(f"{name}: missing tests/")
    return problems


def main() -> int:
    folders = sorted(p for p in (ROOT / "agents").iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    problems = [problem for folder in folders for problem in check(folder)]
    for problem in problems:
        print(f"✗ {problem}")
    if not problems:
        print(f"✓ {len(folders)} agent folders valid: {', '.join(f.name for f in folders)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
