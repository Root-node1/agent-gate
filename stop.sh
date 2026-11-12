#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# AgentGate — Local Development Stop Script
# =============================================================================
# Stops the Django backend and Vite frontend started by run.sh.
# Does NOT stop the PostgreSQL container (it may be shared).
# Usage:
#   ./stop.sh
# =============================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$ROOT/.run-pids"

# ---------------------------------------------------------------------------
# Colors (safe fallback)
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  RED='\033[0;31m'
  CYAN='\033[0;36m'
  NC='\033[0m'
else
  GREEN='' YELLOW='' RED='' CYAN='' NC=''
fi

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; }

# ---------------------------------------------------------------------------
# Stop a process by PID file
# ---------------------------------------------------------------------------
stop_process() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"

  if [ ! -f "$pid_file" ]; then
    info "${name}: no PID file found (not running via run.sh)"
    return
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"

  if [ -z "$pid" ]; then
    info "${name}: empty PID file"
    rm -f "$pid_file"
    return
  fi

  if kill -0 "$pid" 2>/dev/null; then
    # Kill the entire process group (including child processes)
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    # Wait up to 5 seconds for graceful shutdown
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 5 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    # Force kill if still running
    if kill -0 "$pid" 2>/dev/null; then
      warn "${name}: force-killing PID $pid"
      kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    fi
    info "${name}: stopped (PID $pid)"
  else
    info "${name}: process $pid not running (already stopped)"
  fi

  rm -f "$pid_file"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [ ! -d "$PID_DIR" ]; then
  info "No running processes found (PID directory does not exist)"
  echo ""
  echo -e "  ${CYAN}PostgreSQL container:${NC} may still be running as 'agentgate-dev-pg'"
  echo -e "  ${CYAN}To stop it:${NC} docker stop agentgate-dev-pg"
  exit 0
fi

echo -e "${YELLOW}Stopping AgentGate...${NC}"

stop_process "frontend"
stop_process "backend"

# Clean up remaining PID directory
rm -rf "$PID_DIR"

echo ""
info "AgentGate stopped."
echo ""
echo -e "  ${CYAN}PostgreSQL container:${NC} 'agentgate-dev-pg' keeps running."
echo -e "  ${CYAN}To stop it:${NC} docker stop agentgate-dev-pg"
echo ""
echo -e "  ${CYAN}Logs are preserved at:${NC} $PID_DIR (if they existed)"
