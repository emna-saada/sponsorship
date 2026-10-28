#!/usr/bin/env bash
# Start the Live Call Translator (Mac/Linux). First run creates the venv.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi
[ -f .env ] || cp .env.example .env

source .venv/bin/activate
PORT=$(grep -E '^PORT=' .env | cut -d= -f2); PORT=${PORT:-8000}
URL="http://localhost:$PORT"
( for i in $(seq 1 120); do curl -s -o /dev/null "http://127.0.0.1:$PORT/api/status" && break; sleep 1; done; if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL"; fi ) >/dev/null 2>&1 &
echo "Starting on $URL (Ctrl+C to stop)"
exec python -m app.server
