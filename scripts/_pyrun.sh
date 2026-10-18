#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$SCRIPT_DIR/../.venv/Scripts/python.exe" ]; then
  PY="$SCRIPT_DIR/../.venv/Scripts/python.exe"
elif [ -x "$SCRIPT_DIR/../.venv/bin/python" ]; then
  PY="$SCRIPT_DIR/../.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
elif command -v py >/dev/null 2>&1; then
  exec py -3 "$@"
else
  # PATH lookup failed — probe standard Windows install locations.
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  if [ -z "$PY" ]; then
    echo "[ai-log] Python not found; hook was not executed." >&2
    exit 1
  fi
fi

exec "$PY" "$@"
