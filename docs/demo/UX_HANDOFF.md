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
- **Docker** (recommended) or **PostgreSQL 17** installed locally
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
└── run.sh                # Local dev startup script
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Root-node1/agent-gate.git
cd agent-gate
git checkout release/v0.1.0-ux-demo
```

### 2. Start PostgreSQL 17

**Option A — Docker (recommended):**

```bash
docker run --rm -d --name agentgate-demo-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17

export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
```

**Option B — Host PostgreSQL 17:**

```bash
psql -h 127.0.0.1 -p 5432 -U postgres -c "CREATE ROLE agentgate WITH LOGIN PASSWORD 'agentgate-local-only';"
psql -h 127.0.0.1 -p 5432 -U postgres -c "CREATE DATABASE agentgate OWNER agentgate;"
export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:5432/agentgate'
```

### 3. Start the application

```bash
./run.sh
```

This creates the Python venv, installs dependencies, applies migrations, and starts both servers:
- **Backend**: http://localhost:8000
- **Frontend**: http://localhost:5173

Press Ctrl+C to stop both servers.

## Environment Configuration

`run.sh` creates `backend/.env` from `backend/.env.example` on first run with a fresh `DJANGO_SECRET_KEY`. For manual setup:

```bash
cp backend/.env.example backend/.env
```

Key settings in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `DJANGO_SECRET_KEY` | Auto-generated | Django secret key |
| `DEMO_MODE` | `false` | Enable anonymous demo access |
| `PAYMENT_EXECUTOR` | `fake` | Payment executor (`fake` = no PayPal calls) |

**No PayPal credentials are needed for local development or the UI demo.**

## Database Setup

Migrations are applied automatically by `run.sh`. To run them manually:

```bash
cd backend && source venv/bin/activate
python manage.py migrate
```

To create a demo agent with sample data:

```bash
python manage.py seed_demo
```

To create an admin user for the Django admin:

```bash
python manage.py createsuperuser
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

| Problem | Solution |
|---|---|
| `run.sh` fails on first run | Ensure Python 3.13+ and Node 22+ are installed |
| Migration errors | Verify PostgreSQL 17 is running and `DATABASE_URL` is set |
| Frontend won't start | Run `cd frontend && npm install` manually |
| Backend port 8000 in use | Stop existing process or change port in `run.sh` |
| Frontend can't reach API | Ensure backend is running on port 8000 |
| Docker PostgreSQL not ready | Wait for `pg_isready` to succeed before starting app |
| Email verification stuck | Check backend terminal for the verification code |

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
| Full local app startup against PG 17 | Not tested (host has PG 18.6) | Use Docker option in LOCAL_SETUP.md |
| Live PayPal Sandbox API operation | Not tested | Requires founder's PayPal sandbox credentials |
| PayPal AI Toolkit installation | Not installed | UX person installs with their own account |
| PayPal MCP connection | Not configured | UX person connects with their own token |

None of these gaps prevent running the built-in dashboard demo, which is entirely
client-side and does not call PayPal.
