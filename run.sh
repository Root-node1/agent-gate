#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# AgentGate — Local Development Startup Script
# =============================================================================
# Starts PostgreSQL (via Docker), the Django backend, and the Vite frontend.
# Usage:
#   ./run.sh
# Stop with Ctrl+C or:
#   ./stop.sh
# =============================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PID_DIR="$ROOT/.run-pids"

# ---------------------------------------------------------------------------
# Cross-platform Python path
# ---------------------------------------------------------------------------
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PY="$BACKEND/venv/Scripts/python"; SYS_PY=python ;;
  *) PY="$BACKEND/venv/bin/python"; SYS_PY=python3 ;;
esac

# ---------------------------------------------------------------------------
# Colors and formatting (safe fallback when not a terminal)
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  RED='\033[0;31m'
  CYAN='\033[0;36m'
  BOLD='\033[1m'
  NC='\033[0m'
else
  GREEN='' YELLOW='' RED='' CYAN='' BOLD='' NC=''
fi

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; }
step()  { echo -e "${CYAN}==> ${BOLD}$*${NC}"; }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
step "Checking prerequisites"

for cmd in "$SYS_PY" node git; do
  if ! command -v "$cmd" &>/dev/null; then
    error "Required command not found: $cmd"
    exit 1
  fi
done

# Docker is required for the local PostgreSQL service
if ! command -v docker &>/dev/null; then
  error "Docker is required for the local database."
  echo "  Install Docker: https://docs.docker.com/get-docker/"
  exit 1
fi

# Check Docker daemon is running
if ! docker info &>/dev/null; then
  error "Docker daemon is not running. Start Docker and try again."
  exit 1
fi

info "Prerequisites OK (Python $(python3 --version 2>&1), Node $(node --version), Docker $(docker --version 2>&1))"

# ---------------------------------------------------------------------------
# Environment file
# ---------------------------------------------------------------------------
step "Checking environment"

if [ ! -f "$BACKEND/.env" ]; then
  warn "backend/.env not found — creating from .env.example"

  if [ ! -d "$BACKEND/venv" ]; then
    step "Creating Python venv and installing backend dependencies"
    "$SYS_PY" -m venv "$BACKEND/venv"
  fi

  "$PY" -m pip install --upgrade pip &>/dev/null
  "$PY" -m pip install django python-dotenv &>/dev/null

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
  info "Created backend/.env with a random secret key"
else
  info "backend/.env exists"
fi

# ---------------------------------------------------------------------------
# Ensure DATABASE_URL is set
# ---------------------------------------------------------------------------
# Source .env to pick up DATABASE_URL if present
set -a
# shellcheck disable=SC1091
source "$BACKEND/.env" 2>/dev/null || true
set +a

PG_CONTAINER="agentgate-dev-pg"
PG_PORT=55432
PG_USER="agentgate"
PG_PASS="agentgate-local-only"
PG_DB="agentgate"
EXPECTED_DB_URL="postgresql://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${PG_DB}"

if [ -z "${DATABASE_URL:-}" ]; then
  warn "DATABASE_URL is not set — will start PostgreSQL via Docker"
  DATABASE_URL="$EXPECTED_DB_URL"
  export DATABASE_URL
fi

# ---------------------------------------------------------------------------
# Start PostgreSQL via Docker
# ---------------------------------------------------------------------------
step "Starting PostgreSQL"

# Derive the host/port from DATABASE_URL so we can find the right container
DB_HOST="$(echo "$DATABASE_URL" | sed -n 's|.*://[^@]*@\([^:]*\).*/.*|\1|p')"
DB_PORT="$(echo "$DATABASE_URL" | sed -n 's|.*://[^@]*@[^:]*:\([0-9]*\)/.*|\1|p')"

# If DATABASE_URL points to our expected Docker port, try to manage the container
if [ "$DB_HOST" = "127.0.0.1" ] && [ "$DB_PORT" = "$PG_PORT" ]; then

  # Check if the primary container name is running
  if docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    info "PostgreSQL container '${PG_CONTAINER}' is already running"
    PG_RUNNING_CONTAINER="$PG_CONTAINER"

  elif docker ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    # Container exists but is stopped — restart it (preserves data volume)
    info "Restarting stopped PostgreSQL container '${PG_CONTAINER}'"
    docker start "$PG_CONTAINER"
    PG_RUNNING_CONTAINER="$PG_CONTAINER"

  else
    # Look for any container that is already listening on our port with matching credentials
    EXISTING=""
    for name in $(docker ps --format '{{.Names}}'); do
      # Check if this container maps our port
      if docker port "$name" 2>/dev/null | grep -q ":${PG_PORT}"; then
        # Check if it has the right user/db env vars
        ENV_VARS="$(docker inspect "$name" --format '{{range .Config.Env}}{{.}} {{end}}' 2>/dev/null)"
        if echo "$ENV_VARS" | grep -q "POSTGRES_USER=${PG_USER}" \
          && echo "$ENV_VARS" | grep -q "POSTGRES_DB=${PG_DB}"; then
          EXISTING="$name"
          # Extract the actual password from the container so DATABASE_URL is correct
          EXISTING_PASS="$(echo "$ENV_VARS" | sed -n 's/.*POSTGRES_PASSWORD=\([^ ]*\).*/\1/p')"
          if [ -n "$EXISTING_PASS" ]; then
            PG_PASS="$EXISTING_PASS"
            DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${PG_DB}"
            export DATABASE_URL
          fi
          break
        fi
      fi
    done

    if [ -n "$EXISTING" ]; then
      info "Reusing existing PostgreSQL container '${EXISTING}' on port ${PG_PORT}"
      PG_RUNNING_CONTAINER="$EXISTING"
    else
      # First time — create the container with a named volume for persistence
      info "Starting PostgreSQL container '${PG_CONTAINER}' (first time)"
      docker run --rm -d \
        --name "$PG_CONTAINER" \
        -e POSTGRES_USER="$PG_USER" \
        -e POSTGRES_PASSWORD="$PG_PASS" \
        -e POSTGRES_DB="$PG_DB" \
        -p "127.0.0.1:${PG_PORT}:5432" \
        -v "agentgate-dev-pg-data:/var/lib/postgresql/data" \
        postgres:17
      PG_RUNNING_CONTAINER="$PG_CONTAINER"
    fi
  fi

  # Wait for PostgreSQL to be ready
  step "Waiting for PostgreSQL to be ready"
  MAX_WAIT=60
  ELAPSED=0
  while [ $ELAPSED -lt $MAX_WAIT ]; do
    if docker exec "$PG_RUNNING_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB" &>/dev/null; then
      info "PostgreSQL is ready (${ELAPSED}s)"
      break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
  done

  if [ $ELAPSED -ge $MAX_WAIT ]; then
    error "PostgreSQL did not become ready within ${MAX_WAIT}s"
    echo "  Check logs: docker logs $PG_RUNNING_CONTAINER"
    exit 1
  fi

  info "Using PostgreSQL container '${PG_RUNNING_CONTAINER}'"

else
  # DATABASE_URL points somewhere else (host PostgreSQL or different container)
  info "DATABASE_URL points to ${DB_HOST}:${DB_PORT} — skipping Docker PostgreSQL"
fi

# ---------------------------------------------------------------------------
# Python venv and dependencies
# ---------------------------------------------------------------------------
if [ ! -d "$BACKEND/venv" ]; then
  step "Creating Python venv and installing backend dependencies"
  "$SYS_PY" -m venv "$BACKEND/venv"
  "$PY" -m pip install --upgrade pip &>/dev/null
fi

# Always ensure requirements are up to date (fast if already installed)
step "Ensuring backend dependencies are installed"
"$PY" -m pip install -q -r "$BACKEND/requirements.txt"

# ---------------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------------
if [ ! -d "$FRONTEND/node_modules" ]; then
  step "Installing frontend dependencies"
  (cd "$FRONTEND" && npm install)
fi

# ---------------------------------------------------------------------------
# Database migrations
# ---------------------------------------------------------------------------
step "Applying database migrations"
export DJANGO_SETTINGS_MODULE=config.settings.dev
"$PY" "$BACKEND/manage.py" migrate --noinput

info "Migrations applied successfully"

# ---------------------------------------------------------------------------
# Create PID directory for process tracking
# ---------------------------------------------------------------------------
mkdir -p "$PID_DIR"

# ---------------------------------------------------------------------------
# Cleanup handler — stop child processes on Ctrl+C
# ---------------------------------------------------------------------------
BACKEND_PID=""
FRONTEND_PID=""
PG_RUNNING_CONTAINER="${PG_RUNNING_CONTAINER:-$PG_CONTAINER}"

cleanup() {
  echo ""
  warn "Shutting down AgentGate..."

  # Kill process groups (including child processes)
  for label_pid in "Frontend:$FRONTEND_PID" "Backend:$BACKEND_PID"; do
    local label="${label_pid%%:*}"
    local pid="${label_pid##*:}"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      # Kill the entire process group
      kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      info "$label stopped"
    fi
  done

  # Clean up PID files
  rm -rf "$PID_DIR"

  local pg_name="${PG_RUNNING_CONTAINER:-$PG_CONTAINER}"
  info "AgentGate stopped. PostgreSQL container '${pg_name}' keeps running."
  info "  To stop it: docker stop $pg_name"
  info "  Or use: ./stop.sh"
}

trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Start backend
# ---------------------------------------------------------------------------
step "Starting Django backend on port 8000"
setsid "$PY" "$BACKEND/manage.py" runserver 8000 >"$PID_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_DIR/backend.pid"

# Wait for backend to be healthy
step "Waiting for backend to respond"
ELAPSED=0
MAX_WAIT=30
while [ $ELAPSED -lt $MAX_WAIT ]; do
  if curl -sf http://127.0.0.1:8000/healthz &>/dev/null; then
    info "Backend is healthy (${ELAPSED}s)"
    break
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
  error "Backend did not start within ${MAX_WAIT}s"
  echo "  Check logs: cat $PID_DIR/backend.log"
  cleanup
  exit 1
fi

# ---------------------------------------------------------------------------
# Start frontend
# ---------------------------------------------------------------------------
step "Starting Vite frontend on port 5173"
setsid bash -c "cd '$FRONTEND' && npm run dev" >"$PID_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$PID_DIR/frontend.pid"

# Wait for frontend to be ready
ELAPSED=0
MAX_WAIT=20
while [ $ELAPSED -lt $MAX_WAIT ]; do
  if curl -sf http://127.0.0.1:5173/ &>/dev/null; then
    info "Frontend is ready (${ELAPSED}s)"
    break
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
  warn "Frontend did not respond within ${MAX_WAIT}s — check $PID_DIR/frontend.log"
fi

# ---------------------------------------------------------------------------
# Display status
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}AgentGate is running!${NC}"
echo ""
echo -e "  ${CYAN}Frontend:${NC}  http://localhost:5173"
echo -e "  ${CYAN}Backend:${NC}   http://localhost:8000"
echo -e "  ${CYAN}Database:${NC}  PostgreSQL (Docker: ${PG_CONTAINER})"
echo ""
echo -e "  ${YELLOW}Logs:${NC}    $PID_DIR/backend.log"
echo -e "  ${YELLOW}Logs:${NC}    $PID_DIR/frontend.log"
echo ""
echo -e "  ${YELLOW}Stop:${NC}    Press Ctrl+C  or  ./stop.sh"
echo ""

# ---------------------------------------------------------------------------
# Keep running — wait for foreground process
# ---------------------------------------------------------------------------
wait
