# AgentGate Documentation

Working documentation for the team. The README covers setup; this file covers how the system is designed and how we work. Update it in the same PR that changes the behavior.

## 1. Overview

AgentGate sits between an AI agent and PayPal. The agent never holds PayPal credentials. It sends a spend request to AgentGate, which decides **allow**, **deny**, or **needs_approval**, then executes approved payments through PayPal and records everything in an audit log.

Principle: rules are enforced by deterministic code. The AI model is advisory only (for example, flagging injection language), so it cannot be talked out of a limit.

## 2. Architecture

    AI agent --> AgentGate API (Django) --> PayPal (sandbox)
                      |
                      +--> Rule engine (budgets, caps, merchant lists, thresholds)
                      +--> Injection classifier (advisory)
                      +--> Approval queue (human in the dashboard)
                      +--> Audit log (append-only)
                      ^
                      |
              Dashboard (React + TypeScript)

- **backend/**: Django + DRF. Policy engine, API, approvals, audit log, PayPal client, webhooks.
- **frontend/**: Vite + React + TypeScript. Approval queue, policy editor, audit log, activity feed.
- **Dev proxy**: the frontend dev server forwards `/api` to Django on port 8000, so there is no CORS setup in development.

## 3. Request flow

1. The agent submits a spend request (amount, currency, merchant, purpose, where the instruction came from).
2. The rule engine checks: merchant allow/block list, per-transaction cap, daily and monthly budget, velocity, currency, new-payee cooldown.
3. If the instruction came from untrusted content (a web page, email, invoice), the request is escalated.
4. The injection classifier scores the request. It can raise risk but never lowers a rule-based denial.
5. Decision: allow, deny, or needs_approval, with reasons and matching rule IDs.
6. If needs_approval, a human approves or denies in the dashboard.
7. If allowed or approved, AgentGate executes the payment through PayPal.
8. Every step is written to the audit log.

## 4. Data model (planned)

- **Agent**: id, name, API key, status
- **Policy**: agent, daily budget, monthly budget, per-transaction cap, approval threshold, currency
- **MerchantRule**: policy, merchant identifier, allow or block
- **SpendRequest**: agent, amount, currency, merchant, purpose, source, risk score, decision, reasons, matching rules, PayPal reference, timestamps
- **Approval**: spend request, approver, outcome, note, timestamp
- **AuditEvent**: append-only record of every request, decision, approval, and PayPal result

## 5. API (planned unless marked built)

- `GET /api/health/` (built): returns `{"status": "ok"}`
- `POST /v1/spend-requests`: submit a request, receive the decision
- `GET /v1/spend-requests/{id}`: status
- `POST /v1/approvals/{id}/approve` and `/deny`
- `GET/PUT /v1/policies`: manage rules
- `GET /v1/audit`: filterable log
- `POST /webhooks/paypal`: payment events

The OpenAPI schema is generated with drf-spectacular and used to generate the SDK.

## 6. Dashboard screens (planned)

1. Approval queue
2. Policy editor
3. Audit log table
4. Live activity feed

## 7. Configuration and secrets

- Config is read from environment variables, loaded from a local `.env` file (git-ignored).
- Never commit PayPal credentials, API keys, or the Django `SECRET_KEY`. A secret in git history is permanent.
- A `.env.example` with placeholder values will be committed so teammates know what to set.
- PayPal: sandbox only. Never put live credentials in this project.

## 8. Git workflow

- `main` is protected: changes arrive by pull request, with the `backend` and `frontend` checks passing.
- One branch per task, named like `feat/rule-engine` or `fix/audit-order`.
- Commit messages follow the pattern `type(scope): message`, for example `feat(backend): add per-transaction cap rule`. Types: feat, fix, docs, chore, ci, test.
- Keep pull requests small and get at least one review.

## 9. Testing and CI

Run locally before pushing:

    cd backend && source venv/bin/activate && ruff check . && python manage.py test
    cd frontend && npm run lint && npm run build

GitHub Actions runs the same checks on every push and pull request. Every rule in the policy engine gets a unit test.

## 10. Deployment (planned)

- Hosted on Render. Backend and dashboard deployed from `main`.
- Environment variables are set in Render, not in the repo.
- The demo URL must open without a login.

## 11. Decisions log

- **Django over Spring Boot**: the PayPal AI Toolkit supports Python and TypeScript, so the agent layer lives inside the Django service as one backend.
- **Deterministic rules over model judgment**: limits cannot be argued away by text.
- **SQLite for now**: switch to PostgreSQL when the models land.
- **Python env named `venv`** inside `backend/`.
- **SSH to GitHub over port 443**: some networks block port 22.

## 12. Status

- [x] Repo, MIT license, .gitignore
- [x] Django skeleton with health endpoint
- [x] React + TypeScript skeleton with API proxy
- [x] run.sh starts both servers
- [x] GitHub Actions CI
- [x] README
- [ ] Models and rule engine
- [ ] Spend request API and approvals
- [ ] PayPal sandbox payment execution and webhooks
- [ ] Demo agent and injection classifier
- [ ] Dashboard screens
- [ ] Deploy on Render
- [ ] SDK generated from the OpenAPI schema

## 13. PayPal Cart API (agentic commerce) notes

Source: PayPal's Postman collection for validating the merchant Cart API. Summary only; the collection and its linked OpenAPI spec are the reference.

- **What it is:** a client that tests a merchant's own endpoints. PayPal's agentic checkout calls the merchant, not the other way round.
- **Endpoints a merchant implements:** `POST /merchant-cart`, `GET` and `PUT /merchant-cart/{cartId}`, `POST /merchant-cart/{cartId}/checkout`.
- **Flow:** create cart, update cart (optional), approve token (`ec_token`, approved by a sandbox personal account), checkout with `payer_id`.
- **Latency limits:** under 3 seconds, and under 5 seconds for checkout.
- **Auth:** PayPal-issued JWT. In sandbox we sign our own RS256 JWT with a self-generated key pair. In production PayPal signs and publishes its key via JWKS.
- **Error scenarios it tests:** item not found, out of stock, payment declined, shipping not available, invalid JWT, multi-item errors (422 or 200 INCOMPLETE).
- **Sandbox `payer_id`:** create a Personal sandbox account in the PayPal Developer Dashboard; its Account ID is the `payer_id`.

How this relates to AgentGate:

- AgentGate sits on the buyer side, between the agent and PayPal. This collection covers the seller side.
- The approve-token and checkout steps are the moments the firewall should gate.
- A spec-compliant demo merchant is a stretch goal for the Tech Lead after the rule engine and payment execution work. It is not part of the MVP.
- Never commit signing keys. `*.pem` and `*.key` are git-ignored; keys and PayPal credentials live in `.env`. Use sandbox only.
