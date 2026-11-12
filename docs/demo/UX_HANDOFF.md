# AgentGate — UX Designer Handoff

## Project Overview

**AgentGate** is a spend-control firewall between AI agents and payment providers. When an AI agent wants to make a payment, it asks AgentGate first. AgentGate evaluates the request against deterministic policy rules (budgets, merchant allow/block lists, approval thresholds) and decides **allow**, **deny**, or **needs human approval**. Every decision is recorded in an immutable audit log.

The dashboard is the human operator's control panel: approve or deny pending requests, configure agent policies, review audit logs, and monitor activity.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Django + Django REST Framework (Python 3.13) |
| Frontend | React 19 + TypeScript (Vite 8) |
| Database | PostgreSQL 17 |
| Background Jobs | Procrastinate (Redis 7) |
| Styling | CSS custom properties (design tokens), no CSS framework |
| Icons | Lucide React |
| Fonts | Inter Variable |

## Prerequisites

- **Git**
- **Python 3.13+**
- **Node.js 22+**
- **Docker** (required — starts the local PostgreSQL database automatically)
- **Docker Compose** (for deployment testing)

## Repository Structure

```
agent-gate/
├── backend/              # Django application
│   ├── apps/             # Django apps (accounts, agents, policies, spend, etc.)
│   ├── engine/           # Pure Python rule engine (no Django imports)
│   ├── config/           # Django settings (dev, test, prod)
│   └── tests/            # Backend tests
├── frontend/             # React SPA
│   ├── src/
│   │   ├── api/          # API client, typed endpoints, hooks
│   │   ├── pages/        # Page components (app, auth, landing, live)
│   │   ├── session/      # Auth context and route guards
│   │   ├── ui/           # Shared UI components
│   │   ├── tokens.css    # Design tokens (colors, typography, spacing)
│   │   └── styles/       # Global styles
│   └── tests/            # Frontend tests
├── deploy/               # Caddy config, deployment scripts
├── docs/                 # Documentation
│   ├── architecture/     # System architecture
│   ├── design-system/    # Design system reference
│   ├── demo/             # Demo setup and walkthrough
│   └── deployment/       # Deployment guide
├── compose.yaml          # Docker Compose (Caddy, web, worker, Redis)
├── Dockerfile            # Backend production image
├── run.sh                # One-command local dev startup
└── stop.sh               # Stop local dev servers
```

## Quick Start

The fastest way to run AgentGate locally is a single command. `run.sh` handles
everything: installing dependencies, starting the database, running migrations,
and launching both servers.

### 1. Clone the repository

```bash
git clone https://github.com/Root-node1/agent-gate.git
cd agent-gate
git checkout release/v0.1.0-ux-demo
```

### 2. Start the application

```bash
chmod +x run.sh stop.sh
./run.sh
```

That's it. The script will:

1. Check that Python 3.13+, Node.js 22+, and Docker are installed.
2. Create a Python virtual environment and install backend dependencies (first run).
3. Install frontend npm dependencies (first run).
4. Create `backend/.env` with a random secret key (first run).
5. Start a PostgreSQL 17 database container (reused on subsequent runs).
6. Wait for the database to be ready.
7. Apply database migrations.
8. Start the Django backend on port 8000.
9. Start the Vite frontend on port 5173.
10. Display the URLs and confirm everything is running.

Expected output:

```
AgentGate is running!

  Frontend:  http://localhost:5173
  Backend:   http://localhost:8000
  Database:  PostgreSQL (Docker: agentgate-dev-pg)

  Logs:    .run-pids/backend.log
  Logs:    .run-pids/frontend.log

  Stop:    Press Ctrl+C  or  ./stop.sh
```

### 3. Open the application

Open **http://localhost:5173** in your browser.

### Stop the application

Press **Ctrl+C** in the terminal, or run in a second terminal:

```bash
./stop.sh
```

This stops the backend and frontend but leaves the PostgreSQL container running
so your data persists between sessions. To also stop the database:

```bash
docker stop agentgate-dev-pg
```

### Alternative: Host-installed PostgreSQL

If you prefer to run PostgreSQL on your host instead of via Docker, create the
database manually and set `DATABASE_URL` in `backend/.env`:

```bash
psql -h 127.0.0.1 -p 5432 -U postgres <<SQL
CREATE ROLE agentgate WITH LOGIN PASSWORD 'agentgate-local-only';
CREATE DATABASE agentgate OWNER agentgate;
SQL
```

Then edit `backend/.env` and set:

```
DATABASE_URL=postgresql://agentgate:agentgate-local-only@127.0.0.1:5432/agentgate
```

`run.sh` will detect the existing `DATABASE_URL` and skip starting the Docker
container.

## Environment Configuration

`run.sh` creates `backend/.env` from `backend/.env.example` on first run with a
fresh `DJANGO_SECRET_KEY` and the default `DATABASE_URL`. No manual configuration
is needed for basic local development.

For manual setup:

```bash
cp backend/.env.example backend/.env
```

Key settings in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate` | PostgreSQL connection (auto-set by run.sh) |
| `DJANGO_SECRET_KEY` | Auto-generated | Django secret key |
| `DEMO_MODE` | `false` | Enable anonymous demo access |
| `PAYMENT_EXECUTOR` | `fake` | Payment executor (`fake` = no PayPal calls) |

**No PayPal credentials are needed for local development or the UI demo.**

## Database Setup

Migrations are applied automatically by `run.sh`. The PostgreSQL database runs in
a Docker container with a named volume (`agentgate-dev-pg-data`), so your data
persists between sessions.

To run migrations manually:

```bash
cd backend && source venv/bin/activate
python manage.py migrate
```

To create a demo agent with sample data (for the Live API tester):

```bash
python manage.py seed_demo
```

To create an admin user for the Django admin:

```bash
python manage.py createsuperuser
```

To reset the local database (destroys all local data):

```bash
docker stop agentgate-dev-pg
docker rm agentgate-dev-pg
docker volume rm agentgate-dev-pg-data
# Then run ./run.sh again to start fresh
```

## Test Accounts

For the demo, register a new account at http://localhost:5173/login. The email verification code appears in the backend terminal output. No pre-configured test accounts exist — create your own.

## Running Tests

### Backend

```bash
cd backend && source venv/bin/activate
python manage.py test          # SQLite (fast)
ruff check .                   # Linting
mypy --strict engine/          # Type checking
```

### Frontend

```bash
cd frontend
npm run lint                   # ESLint
npm run build                  # Production build
node --test tests/*.test.mjs   # Unit tests
```

## Important Routes & Pages

### Public Pages (no login required)

| Route | Description |
|---|---|
| `/` | Landing page |
| `/system-requirements` | Desktop client system requirements |
| `/downloads` | Download page |
| `/installation` | Installation guide |

### Authentication Pages

| Route | Description |
|---|---|
| `/login` | Sign in |
| `/register` | Create account |
| `/forgot-password` | Password reset |
| `/verify-email` | Email verification |

### Dashboard Pages (requires login)

| Route | Description |
|---|---|
| `/app` | Overview dashboard |
| `/app/agents` | Agent management |
| `/app/approvals` | Approval queue |
| `/app/transactions` | Transaction history |
| `/app/policies` | Policy configuration |
| `/app/audit` | Audit log |
| `/app/settings` | Account and team settings |
| `/app/simulate` | Policy simulator |

### Live API Tester

| Route | Description |
|---|---|
| `/live` | Live API request tester |
| `/live/tester` | Interactive tester |

## Design System

The design system is documented in [docs/design-system/OVERVIEW.md](design-system/OVERVIEW.md). Key files:

- **`frontend/src/tokens.css`** — All CSS custom properties (colors, typography, spacing, shadows)
- **`frontend/src/ui/`** — Shared components (Badges, Cards, Modals, Toasts, Layout)
- **`frontend/src/api/useApiResource.ts`** — Hook for loading/error/empty states

### Key Design Conventions

1. **Decisions are never color-only** — every status has an icon + label + color.
2. **Use design tokens** — never hardcode colors; use `var(--color-*)` from `tokens.css`.
3. **Handle all API states** — every page shows loading, error, and empty states via `useApiResource`.
4. **Accessibility** — WCAG AA contrast, `:focus-visible` indicators, `prefers-reduced-motion` support.
5. **Consistent feedback** — hover, focus, and active states follow the same pattern.

## Existing UX Conventions

- **Loading states**: Spinner or skeleton while data is fetching.
- **Error states**: `ApiError` component with message and retry button.
- **Empty states**: `EmptyState` component with contextual message and action.
- **Form validation**: Inline field errors, `disabled={isSubmitting}` on submit buttons.
- **Toast notifications**: Non-blocking success/error feedback.
- **404 page**: Branded page with multiple recovery actions (home, dashboard, go back).

## Known Limitations & Incomplete Integrations

1. **PayPal sandbox transactions** — Payment execution defaults to `fake` mode. No actual PayPal calls are made. Sandbox transaction verification is pending external ownership.
2. **Demo mode** — `DEMO_MODE=true` enables anonymous read access to demo data. Write operations (approve/deny) require explicit enable.
3. **Browser auth journeys** — Login, signup, MFA, and password reset flows have been verified by automated tests but may not have been confirmed in a live browser session.
4. **Tauri desktop** — Desktop packaging exists but is unsigned and not distributed.
5. **Production deployment** — Contabo VPS deployment is configured but not yet active.

## Troubleshooting

### Viewing logs

When `run.sh` is running, logs are written to `.run-pids/`:

```bash
# Backend logs
tail -f .run-pids/backend.log

# Frontend logs
tail -f .run-pids/frontend.log
```

### Common issues

| Problem | Solution |
|---|---|
| `run.sh` fails: Python not found | Install Python 3.13+: `https://www.python.org/downloads/` |
| `run.sh` fails: Node not found | Install Node.js 22+: `https://nodejs.org/` |
| `run.sh` fails: Docker not found | Install Docker: `https://docs.docker.com/get-docker/` |
| `run.sh` fails: Docker daemon not running | Start the Docker Desktop application or `sudo systemctl start docker` |
| Migration errors | Check `.run-pids/backend.log` for details; verify `DATABASE_URL` in `backend/.env` |
| Frontend won't start | Check `.run-pids/frontend.log`; try `cd frontend && npm install` manually |
| Backend port 8000 in use | Stop the existing process: `./stop.sh` |
| Frontend port 5173 in use | Stop the existing process: `./stop.sh` |
| Frontend can't reach API | Ensure backend is running on port 8000; check backend logs |
| PostgreSQL container fails to start | Check `docker logs agentgate-dev-pg`; ensure port 55432 is free |
| Email verification stuck | The verification code appears in the backend log: `tail -f .run-pids/backend.log` |
| Database connection refused after restart | PostgreSQL may need a moment to start; wait and try `./run.sh` again |

### Troubleshooting database startup

```bash
# Check if the container is running
docker ps | grep agentgate-dev-pg

# View database logs
docker logs agentgate-dev-pg

# Check database readiness
docker exec agentgate-dev-pg pg_isready -U agentgate -d agentgate

# Restart the database container
docker restart agentgate-dev-pg
```

### Troubleshooting backend startup

```bash
# Check backend logs
cat .run-pids/backend.log

# Test backend health endpoint
curl http://localhost:8000/healthz

# Test database connectivity
cd backend && source venv/bin/activate
python manage.py check --deploy
```

### Troubleshooting frontend startup

```bash
# Check frontend logs
cat .run-pids/frontend.log

# Test frontend is serving
curl -I http://localhost:5173/

# Reinstall frontend dependencies
cd frontend && rm -rf node_modules && npm install
```

### Resetting the local database

If you need a completely fresh database:

```bash
./stop.sh
docker stop agentgate-dev-pg
docker rm agentgate-dev-pg
docker volume rm agentgate-dev-pg-data
./run.sh
```

⚠️ This destroys all local data, including any accounts or demo data you created.

## Documentation Links

- [Architecture Overview](architecture/OVERVIEW.md) — System architecture and components
- [Design System](design-system/OVERVIEW.md) — Colors, typography, components, conventions
- [Deployment Guide](deployment/CONTABO_DEPLOYMENT.md) — Production deployment on Contabo VPS
- [Demo Walkthrough](demo/DEMO_WALKTHROUGH.md) — Guided demo tour
- [Local Setup](demo/LOCAL_SETUP.md) — Detailed local setup instructions
- [Project Documentation](../../Doc.md) — Working team documentation

**What still needs manual verification before a public demo:**

| Check | Status | Required action |
|---|---|---|
| Browser login/signup/verification flow | Not browser-tested | UX person / founder must run manually |
| Browser MFA enrollment and login | Not browser-tested | UX person / founder must run manually |
| Browser logout + session invalidation | Not browser-tested | UX person / founder must run manually |
| Browser password reset end-to-end | Not browser-tested | UX person / founder must run manually |
| Full local app startup against PG 17 | run.sh starts PG 17 via Docker automatically | Run `./run.sh` and verify both servers start |
| Live PayPal Sandbox API operation | Not tested | Requires founder's PayPal sandbox credentials |
| PayPal AI Toolkit installation | Not installed | UX person installs with their own account |
| PayPal MCP connection | Not configured | UX person connects with their own token |

None of these gaps prevent running the built-in dashboard demo, which is entirely
client-side and does not call PayPal.
