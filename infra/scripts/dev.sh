#!/usr/bin/env bash
# Boot the dev stack: backend (FastAPI) + frontend (Next.js).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Pick a python3.11+ interpreter.
if command -v python3.13 >/dev/null 2>&1; then
  PY=python3.13
elif command -v python3.12 >/dev/null 2>&1; then
  PY=python3.12
elif command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
else
  echo "[dev] Need Python 3.11+; install via Homebrew or pyenv." >&2
  exit 1
fi

# Ensure a venv with backend deps.
if [ ! -d ".venv" ]; then
  echo "[dev] Creating Python venv at .venv..."
  "$PY" -m venv .venv
  ./.venv/bin/pip install -U pip wheel
  ./.venv/bin/pip install -e .
fi

# Ensure frontend deps.
if [ ! -d "frontend/node_modules" ]; then
  echo "[dev] Installing frontend deps..."
  (cd frontend && npm install)
fi

# Kill any stale dev procs on our ports.
lsof -ti :8765 | xargs kill -9 2>/dev/null || true
lsof -ti :3000 | xargs kill -9 2>/dev/null || true

mkdir -p logs

echo "[dev] Starting backend on :8765..."
./.venv/bin/python -m backend.app.main >logs/backend.log 2>&1 &
BACKEND_PID=$!

echo "[dev] Starting frontend on :3000..."
(cd frontend && npm run dev) >logs/frontend.log 2>&1 &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "[dev] Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[dev] Backend pid=$BACKEND_PID  -> http://127.0.0.1:8765"
echo "[dev] Frontend pid=$FRONTEND_PID -> http://127.0.0.1:3000"
echo "[dev] Tail logs: tail -f logs/backend.log logs/frontend.log"
echo "[dev] Press Ctrl-C to stop."

wait
