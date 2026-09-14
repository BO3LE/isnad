#!/usr/bin/env bash
# Run every Python component's own test suite, one at a time, from inside its folder.
# This is what "tested alone" means in GP-plan Part 2.
set -euo pipefail
cd "$(dirname "$0")/.."

status=0
components=(contracts db adapters exporters worker api)
for agent in agents/*/; do components+=("${agent%/}"); done

for component in "${components[@]}"; do
  printf '%-22s' "$component"
  if output=$(cd "$component" && python -m pytest -q -p no:cacheprovider 2>&1); then
    echo "$output" | tail -1
  else
    echo "FAILED"
    echo "$output"
    status=1
  fi
done
exit $status
