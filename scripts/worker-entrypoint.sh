#!/usr/bin/env bash
# Development entrypoint for the worker container.
# Installs any agent folder that isn't installed yet, so "drop a folder into agents/ and
# restart the worker" is all it takes to add an agent (AT-12). Production images install
# every agent at build time instead.
set -euo pipefail
cd /app

for agent in agents/*/; do
  name="gp-agent-$(basename "$agent")"
  if [ -f "$agent/pyproject.toml" ] && ! pip show "$name" >/dev/null 2>&1; then
    echo "installing new agent: $name"
    pip install --quiet -c constraints.txt --config-settings editable_mode=compat -e "$agent"
  fi
done

exec "$@"
