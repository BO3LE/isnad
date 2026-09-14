#!/usr/bin/env bash
# Re-pin constraints.txt from the current .venv (run scripts/bootstrap.sh first, with all extras installed).
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
{
  echo "# Pinned versions for every Python component — the environment the team, CI and Docker share."
  echo "# Regenerate after changing dependencies: scripts/update_constraints.sh"
  pip freeze --exclude-editable | grep -viE "^(gp-|-e )" | sort -f
} > constraints.txt
echo "✓ constraints.txt updated — commit it with your dependency change"
