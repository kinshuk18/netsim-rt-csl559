#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ ! -d ".venv" ]; then
  echo "Error: .venv virtual environment not found in $REPO_DIR."
  echo "Please create it using: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

LOCAL_HOST="127.0.0.1"
LOCAL_PORT="3507"

echo "=== Starting NetSim-RT Local Interactive Demo ==="
echo "Binding to http://${LOCAL_HOST}:${LOCAL_PORT}"
echo "Press Ctrl+C to terminate the server."
echo ""

exec "$REPO_DIR/.venv/bin/uvicorn" server.main:app --host "$LOCAL_HOST" --port "$LOCAL_PORT"
