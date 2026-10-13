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

### Rule engine (built)

Implemented in `backend/gate/rules.py` as a pure function: `evaluate(spend, limits, spent)` returns a decision plus the reasons. It never touches the database or the network, so it is fully deterministic and unit-tested (`gate/test_rules.py`).

Hard rules (any one denies):

- `INVALID_AMOUNT`: amount is zero or negative
- `CURRENCY_MISMATCH`: request currency differs from the policy currency
- `MERCHANT_BLOCKED`: merchant is on the block list
- `MERCHANT_NOT_ALLOWED`: an allow list exists and the merchant is not on it
- `OVER_TRANSACTION_CAP`: amount is above the per-transaction cap
- `OVER_DAILY_BUDGET` and `OVER_MONTHLY_BUDGET`: already-spent plus this amount exceeds the budget

Approval rules (a human must decide):

- `UNTRUSTED_SOURCE`: the instruction came from a web page, email or invoice
- `UNKNOWN_SOURCE`: the origin is unknown (fails closed; only `trusted` can be auto-allowed)
- `OVER_APPROVAL_THRESHOLD`: amount is above the approval threshold

Precedence: any deny wins, then any approval reason gives `needs_approval`, otherwise `allow`. Every triggered rule is reported, so the audit log explains the full decision. Merchants are normalized (lowercase, no scheme, path or `www.`) before matching, and lookalike domains such as `acme.com.evil.net` do not match `acme.com`.

Open question for the Security role: who sets `source`? If the agent labels its own requests `trusted`, an attacker can spoof it. The label should come from the integration layer (SDK or MCP wrapper) based on where the instruction originated.

## 4. Data model (built)

Defined in `backend/gate/models.py`, registered in the Django admin.

- **Agent**: name, `api_key_prefix`, `api_key_hash` (SHA-256; the raw key is shown once by `Agent.create_with_key()` and never stored), status (active or suspended)
- **Policy** (one per agent): currency, `per_transaction_cap`, `approval_threshold`, `daily_budget`, `monthly_budget`. A database constraint requires the threshold to be at or below the cap.
- **MerchantRule**: policy, merchant, action (allow or block), note. A merchant can appear once per policy.
- **SpendRequest** (UUID id): agent, amount, currency, merchant, purpose, source (trusted, untrusted, unknown), `risk_score`, decision (pending, allow, deny, needs_approval), reasons, matched rules, PayPal reference
- **Approval** (one per spend request): outcome (pending, approved, denied), approver, note, decided time
- **AuditEvent**: event type, agent, spend request, JSON payload, created time. Append-only in code: `save()` on an existing row and `delete()` raise `PermissionError`. Create events with `AuditEvent.record(...)`. The admin shows them read-only.

Note: bulk operations like `QuerySet.update()` bypass model methods, so never use them on audit events. A database-level guard may come later.

## 5. API (planned unless marked built)

- `GET /api/health/` (built): returns `{"status": "ok"}`
- `GET /api/schema/` and `/api/docs/` (built): OpenAPI schema and Swagger UI
- `POST /v1/spend-requests/` (built): submit a request. Returns 201 with `decision` (allow, deny or needs_approval), reasons and matched rules in the body
- `GET /v1/spend-requests/{id}/` (built): read one of the agent's own requests
- `POST /v1/approvals/{id}/approve` and `/deny`
- `GET/PUT /v1/policies`: manage rules
- `GET /v1/audit`: filterable log
- `POST /webhooks/paypal`: payment events

The OpenAPI schema is generated with drf-spectacular and used to generate the SDK.

### Agent authentication and the spend request API (built)

- Agents authenticate with `Authorization: Bearer <agent key>`. Keys look like `agk_...`. Only a SHA-256 hash is stored, and suspended agents are rejected.
- Create an agent, its policy and merchant rules with `python manage.py create_agent NAME --allow acme.com --block evil.com --cap 100 --threshold 50 --daily 500 --monthly 5000`. The key is printed once.
- `POST /v1/spend-requests/` takes `amount`, `currency`, `merchant`, optional `purpose`, and `source` (trusted, untrusted or unknown; missing means unknown). The response is HTTP 201 for every decision, so agents and SDKs must read `decision`, never just the status code.
- Budgets count allowed requests plus approvals that are pending or approved. Denied requests and rejected approvals do not count.
- The policy row is locked during a decision (`select_for_update`) so concurrent requests cannot both pass a budget. SQLite ignores the lock; PostgreSQL enforces it.
- Audit events written per request: `spend_request.received`, `spend_request.decided`, and `approval.requested` when a human is needed.
- A request from an agent with no policy returns 409.
- `risk_score` stays 0 until the injection classifier lands.

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

GitHub Actions runs the same checks on every push and pull request. Every rule in the policy engine gets a unit test. Lint settings live in `backend/ruff.toml` (generated migrations are excluded; RUF012 is ignored because Django's `Meta` and admin options are plain class attributes). Keeping the config in the repo makes local runs and CI identical.

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
- **API keys are stored hashed**: only a prefix and SHA-256 hash are kept, so a database leak does not expose agent keys.
- **Audit log is append-only in model code**, and agents are created through `Agent.create_with_key()` rather than the admin.
- **CI fails on missing migrations** (`makemigrations --check`).
- **Rule engine is a pure function**: no database access inside `evaluate`, so every rule is testable in isolation.
- **Fail closed**: only requests from a trusted source can be auto-allowed; unknown or untrusted sources always need a human.
- **Allow list means deny-by-default**: when a policy has an allow list, any other merchant is denied.

## 12. Status

- [x] Repo, MIT license, .gitignore
- [x] Django skeleton with health endpoint
- [x] React + TypeScript skeleton with API proxy
- [x] run.sh starts both servers
- [x] GitHub Actions CI
- [x] README
- [x] Data models, migrations and admin
- [x] Rule engine (pure function, unit-tested)
- [x] Spend request API with agent key auth and audit trail
- [ ] Approval endpoints (approve and deny)
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
