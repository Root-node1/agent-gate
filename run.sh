#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PY="$BACKEND/venv/bin/python"

# First-run setup: Python env
if [ ! -d "$BACKEND/venv" ]; then
  echo "==> Creating Python venv and installing backend deps"
  python3 -m venv "$BACKEND/venv"
  "$BACKEND/venv/bin/pip" install -r "$BACKEND/requirements.txt"
fi

# First-run setup: .env with a fresh secret key
if [ ! -f "$BACKEND/.env" ]; then
  echo "==> Creating backend/.env from .env.example"
  BACKEND="$BACKEND" "$PY" - << 'PYEOF'
import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

backend = Path(os.environ["BACKEND"])
text = (backend / ".env.example").read_text()
text = text.replace(
    "DJANGO_SECRET_KEY=change-me",
    "DJANGO_SECRET_KEY=" + get_random_secret_key(),
)
(backend / ".env").write_text(text)
PYEOF
fi

# First-run setup: frontend deps
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "==> Installing frontend deps"
  (cd "$ROOT/frontend" && npm install)
fi

# Stop both servers on Ctrl+C
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

echo "==> Applying migrations"
"$PY" "$BACKEND/manage.py" migrate --noinput

echo "==> Backend:  http://localhost:8000"
"$PY" "$BACKEND/manage.py" runserver 8000 &

echo "==> Frontend: http://localhost:5173"
(cd "$ROOT/frontend" && npm run dev) &

wait
