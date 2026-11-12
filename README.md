# AgentGate

A spend-control firewall between AI agents and payment providers. The agent asks, AgentGate decides: **allow**, **deny**, or **needs human approval**. Budgets, merchant rules, and approval thresholds are enforced by deterministic code — not by the AI model — and every decision is written to an immutable audit log.

## Core Features

- **Deterministic policy engine** — Rules R01–R16 enforce budgets, caps, merchant allow/block lists, velocity limits, and approval thresholds. The AI model is advisory only and cannot override policy decisions.
- **Approval queue** — Requests that exceed thresholds or trigger risk rules are held for human review. Approvers recheck the current policy before authorizing.
- **Append-only audit log** — Hash-chained per organization with database-level write protection on PostgreSQL. Tamper-evident by default, tamper-proof with external anchoring.
- **Idempotent API** — Every spend request requires an `Idempotency-Key`. Replays return the stored result; conflicting bodies return 409.
- **Dashboard** — React + TypeScript dashboard for managing agents, policies, approvals, transactions, and audit logs.
- **Multi-factor authentication** — TOTP-based MFA with encrypted secrets and recovery codes.
- **Organization isolation** — All data is scoped to the authenticated user's organization memberships. Client-supplied org IDs are never trusted.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Django + Django REST Framework (Python 3.13) |
| Frontend | React 19 + TypeScript (Vite 8) |
| Database | PostgreSQL 17 |
| Background Jobs | Procrastinate (Redis 7 broker) |
| Deployment | Docker Compose + Caddy (auto TLS) |
| Desktop | Tauri 2 (optional wrapper) |

## High-Level Architecture

```
AI Agent → AgentGate API → Rule Engine → Allow / Deny / Needs Approval
                              ↓
                        Audit Log (append-only)
                              ↓
                    PayPal Sandbox (sandbox-only, fake executor by default)

Dashboard (React) → Django Session Auth → Approve / Deny / Configure
```

See [docs/architecture/OVERVIEW.md](docs/architecture/OVERVIEW.md) for the full architecture reference.

## Prerequisites

- **Python 3.13+**
- **Node.js 22+**
- **PostgreSQL 17** (or Docker)
- **Git**

## Quick Local Setup

```bash
git clone https://github.com/Root-node1/agent-gate.git
cd agent-gate
git checkout release/v0.1.0-ux-demo
```

### Start PostgreSQL 17 (Docker recommended)

```bash
docker run --rm -d --name agentgate-demo-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17

export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
```

### Start both servers

```bash
./run.sh
```

- **Backend**: http://localhost:8000
- **Frontend**: http://localhost:5173

`run.sh` creates the Python venv, installs dependencies, applies migrations, and starts both servers on first run. Press Ctrl+C to stop.

## Environment Configuration

`run.sh` creates `backend/.env` from `backend/.env.example` on first run. Key settings:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `DJANGO_SECRET_KEY` | Auto-generated | Django secret key |
| `DEMO_MODE` | `false` | Enable anonymous demo access |
| `PAYMENT_EXECUTOR` | `fake` | Payment executor (`fake` = no PayPal calls) |

No PayPal credentials are needed for local development. See `backend/.env.example` for the full list.

## Running Tests

```bash
# Backend
cd backend && source venv/bin/activate
ruff check .
mypy --strict engine/
python manage.py test

# Frontend
cd frontend
npm run lint
npm run build
node --test tests/*.test.mjs
```

## Documentation

- [Architecture Overview](docs/architecture/OVERVIEW.md) — System architecture, components, API structure
- [Design System](docs/design-system/OVERVIEW.md) — Colors, typography, components, conventions
- [UX Designer Handoff](docs/demo/UX_HANDOFF.md) — Setup guide for UX designers
- [Deployment Guide](docs/deployment/CONTABO_DEPLOYMENT.md) — Production deployment on Contabo VPS
- [Demo Walkthrough](docs/demo/DEMO_WALKTHROUGH.md) — Guided demo tour
- [Working Documentation](Doc.md) — Detailed team reference (data model, rules, API, decisions)

## Deployment

Production deployment uses Docker Compose with Caddy (reverse proxy + TLS), gunicorn (web), Procrastinate (worker), and Redis. PostgreSQL is external (Neon managed). See [compose.yaml](compose.yaml) and [docs/deployment/CONTABO_DEPLOYMENT.md](docs/deployment/CONTABO_DEPLOYMENT.md).

CI/CD runs on GitHub Actions: backend tests against PostgreSQL 17, frontend lint + build + tests, security audit, and deployment config validation.

## Current Status & Known Limitations

- **PayPal sandbox transactions** — Payment execution defaults to `fake` mode. No actual PayPal calls are made during local development or deployment. Sandbox transaction verification is pending external ownership.
- **Production deployment** — Docker Compose configuration is complete and validated in CI, but the Contabo VPS is not yet active.
- **Tauri desktop** — Desktop packaging exists but is unsigned and not distributed.
- **Browser auth journeys** — Login, signup, MFA, and password reset flows are implemented and tested but may need live browser verification.

## License

MIT. See [LICENSE](LICENSE).
