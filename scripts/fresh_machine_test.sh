#!/usr/bin/env bash
# W11: re-run the fresh-machine test documented in docs/fresh-machine-test.md.
#
# Clones this repository's current HEAD into a fresh temp directory (so nothing local —
# .venv, node_modules, .env, docker build cache from a previous run — can hide a broken
# instruction), then follows SETUP.md's Docker path literally: cp .env.example .env,
# docker compose up --build, wait for /health/ready, run scripts/smoke_test.py, tear down.
#
# Usage: scripts/fresh_machine_test.sh [--keep] [--project NAME]
#   --keep            Don't delete the temp clone or stop the stack at the end (for debugging).
#   --project NAME    docker compose project name (default: isnad-fresh-<random>, to avoid
#                      colliding with any stack you already have running).
#
# Uses its own compose project name and DB_HOST_PORT/REDIS_HOST_PORT so it won't collide with an
# already-running `docker compose up` of this repo on those two services. The api (8000) and
# frontend (5173) ports are hardcoded in docker-compose.yml, not parameterized — if something else
# already holds those, this fails the same way SETUP.md's troubleshooting table describes
# ("port is already allocated"); stop the other stack first, or free those two ports.
set -euo pipefail

KEEP=0
PROJECT="isnad-fresh-$$"
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1; shift ;;
    --project) PROJECT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$(mktemp -d -t isnad-fresh-machine-XXXXXX)"
CLONE_DIR="$WORK_DIR/isnad"
LOG="$WORK_DIR/log.txt"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }
now() { date +%s; }

cleanup() {
  local status=$?
  if [ "$KEEP" -eq 1 ]; then
    log "kept: stack (project $PROJECT) and clone at $CLONE_DIR"
    exit "$status"
  fi
  log "tearing down project $PROJECT and deleting $WORK_DIR"
  ( cd "$CLONE_DIR" 2>/dev/null && docker compose -p "$PROJECT" down -v ) >>"$LOG" 2>&1 || true
  rm -rf "$WORK_DIR"
  exit "$status"
}
trap cleanup EXIT

log "cloning HEAD ($(cd "$REPO_ROOT" && git rev-parse --short HEAD)) from $REPO_ROOT into $CLONE_DIR"
git clone --quiet "$REPO_ROOT" "$CLONE_DIR"
cd "$CLONE_DIR"

log "cp .env.example .env"
cp .env.example .env
# Non-default host ports so this can run next to a normal `docker compose up` of the same repo.
{
  echo ""
  echo "DB_HOST_PORT=15433"
  echo "REDIS_HOST_PORT=16379"
} >> .env

BUILD_START=$(now)
log "docker compose -p $PROJECT up --build -d"
MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" up --build -d >>"$LOG" 2>&1
BUILD_END=$(now)
log "build + start took $((BUILD_END - BUILD_START))s"

log "waiting for http://localhost:8000/health/ready"
READY=0
for _ in $(seq 1 120); do
  if curl -fsS http://localhost:8000/health/ready >>"$LOG" 2>&1; then
    READY=1
    break
  fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  log "✗ /health/ready never came up — see $LOG and: docker compose -p $PROJECT logs"
  exit 1
fi
log "✓ /health/ready is up"

log "running scripts/smoke_test.py"
SMOKE_START=$(now)
# On Windows/Git Bash, `python3` often exists on PATH only as the Microsoft Store install stub
# (it "is found" but fails to run) — so probe by actually invoking it, not just `command -v`.
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  log "✗ no working python3/python found on PATH"
  exit 1
fi
log "using interpreter: $PY ($("$PY" --version 2>&1))"
# -X utf8: on native Windows Python, stdout defaults to cp1252 and the script's ✓/✗ output
# crashes with UnicodeEncodeError otherwise (see SETUP.md's Windows notes).
if "$PY" -X utf8 scripts/smoke_test.py 2>&1 | tee -a "$LOG"; then
  log "✓ smoke test passed ($(( $(now) - SMOKE_START ))s)"
else
  log "✗ smoke test failed — see $LOG"
  exit 1
fi

TOTAL_END=$(now)
log "✓ fresh-machine test passed. total time: $((TOTAL_END - BUILD_START))s. log: $LOG"
