#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/strategic-planning/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

export PYTHONPATH="${ROOT_DIR}/backend"
exec "$PYTHON_BIN" -m uvicorn app.main:app \
  --host "${ANALYSIS_HOST:-127.0.0.1}" \
  --port "${ANALYSIS_PORT:-8787}"
