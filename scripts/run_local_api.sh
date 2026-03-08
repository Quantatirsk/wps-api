#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export WPS_WORKSPACE_ROOT="${WPS_WORKSPACE_ROOT:-${PROJECT_ROOT}/workspace}"
export DISPLAY="${DISPLAY:-:99}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-${WPS_WORKSPACE_ROOT}/runtime}"

mkdir -p "$WPS_WORKSPACE_ROOT/jobs" "$XDG_RUNTIME_DIR"

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
