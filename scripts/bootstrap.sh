#!/usr/bin/env bash
# Create .venv and install every Python component in editable mode, plus dev tooling.
# Usage: scripts/bootstrap.sh            (needs Python 3.11+)
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'

[ -d .venv ] || "$PYTHON" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

# compat mode puts each src/ folder on sys.path, which keeps the `agents` namespace package
# resolvable from the repository root (see docs/DECISIONS.md, INF-01).
EDITABLE=(--config-settings editable_mode=compat)
PACKAGES=(-e ./contracts -e ./db -e "./adapters[all]" -e ./exporters -e ./worker -e "./api[test]")
for agent in agents/*/; do
  [ -f "$agent/pyproject.toml" ] && PACKAGES+=(-e "./${agent%/}")
done

python -m pip install --quiet -c constraints.txt "${EDITABLE[@]}" "${PACKAGES[@]}"
python -m pip install --quiet -c constraints.txt -r requirements-dev.txt

echo "✓ .venv ready — activate with: source .venv/bin/activate"
