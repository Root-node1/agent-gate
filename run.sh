#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/venv/bin/python"

# First-run setup
if [ ! -d "$ROOT/backend/venv" ]; then
  echo "==> Creating Python venv and installing backend deps"
  python3 -m venv "$ROOT/backend/venv"
  "$ROOT/backend/venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "==> Installing frontend deps"
  (cd "$ROOT/frontend" && npm install)
fi

# Stop both servers on Ctrl+C
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

echo "==> Applying migrations"
"$PY" "$ROOT/backend/manage.py" migrate --noinput

echo "==> Backend:  http://localhost:8000"
"$PY" "$ROOT/backend/manage.py" runserver 8000 &

echo "==> Frontend: http://localhost:5173"
(cd "$ROOT/frontend" && npm run dev) &

wait
