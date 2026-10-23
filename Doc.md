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
2. The rule engine checks: merchant allow/block list, per-transaction cap, daily, weekly and monthly budgets, velocity, merchant-window spend, currency, provenance and deterministic injection phrases. New-payee checks are planned.
3. If the instruction did not come from a trusted source, the request is escalated or denied according to the policy.
4. A later injection classifier may score the request. It can raise risk but never lower a rule-based denial; deterministic injection phrases are denied today.
5. Decision: allow, deny, or needs_approval, with reasons and matching rule IDs.
6. If needs_approval, a human approves or denies in the dashboard.
7. If allowed or approved, AgentGate executes the payment through PayPal.
8. Every step is written to the audit log.

### Rule engine (built)

Implemented in `backend/engine/` as pure Python. `evaluate(spend, limits, spent)` accepts normalized values and returns a decision plus every rule that fired. It never touches the database, the network, the clock or Django, so it is deterministic and unit-tested (`backend/tests/test_rules.py`). The import contract in `backend/.importlinter` enforces that boundary.

Hard rules (any one denies):

- `R01_AGENT_ACTIVE`: the agent is not active
- `R02_CURRENCY`: request currency differs from the policy currency
- `R03_MERCHANT_BLOCK`: merchant is on the block list
- `R04_MERCHANT_ALLOW`: an allow list exists and the merchant is not on it
- `R05_PER_TX_CAP`: amount is zero, negative, or above the per-transaction cap
- `R06_DAILY_BUDGET` and `R07_MONTHLY_BUDGET`: already-spent plus this amount exceeds the daily or monthly budget
- `R16_WEEKLY_BUDGET`: already-spent this week plus this amount exceeds the weekly budget
- `R14_INJECTION_PATTERN`: the purpose or evidence contains a deterministic override phrase

Approval rules (a human must decide):

- `R08_VELOCITY`: the count of recent budget-consuming requests is already at the policy maximum
- `R09_MERCHANT_WINDOW`: recent budget-consuming spend to this merchant plus this amount exceeds the merchant-window cap
- `R10_APPROVAL_THRESHOLD`: amount is at or above the approval threshold
- `R13_UNTRUSTED_SOURCE`: provenance is anything other than `trusted`; the policy's `untrusted_source_action` can turn this into a deny

Precedence: any deny wins, then any approval reason gives `needs_approval`, otherwise `allow`. Every triggered rule is reported, so the audit log explains the full decision. Merchants are normalized (lowercase, no scheme, path or `www.`) before matching, and lookalike domains such as `acme.com.evil.net` do not match `acme.com`. Messages contain no budgets, caps or spent amounts; numeric policy context belongs in the dashboard and audit views.

Provenance is self-reported. The API cannot prove that `source=trusted` is true; the SDK or MCP wrapper must set it from where the instruction originated. Missing provenance defaults to `untrusted`, and every non-trusted source fails closed.

Deterministic injection screening lives in `engine/screening/patterns.py`. It normalizes NFKC, casefolds, strips zero-width format characters, folds common homoglyphs, and collapses whitespace before matching phrases such as "ignore previous instructions", "override the policy" and "approve this payment". It is a backstop, not a detector: paraphrases can still pass. The classifier remains a later, advisory-only layer: it may escalate and add risk, never deny or lower another rule.

## 4. Data model (built)

Split across `backend/apps/`, registered in the Django admin.

- **User / Organization / OrgMembership** (`apps/accounts`): dashboard users authenticate as a custom `AUTH_USER_MODEL`; each organization has members with a role (admin, approver, viewer). Every operational row carries an `organization` foreign key.
- **Agent / ApiKey** (`apps/agents`): an agent belongs to an organization and has a status (active or suspended). Keys live in a separate table so they can rotate; only a prefix and a SHA-256 hash are stored, `last_used_at`/`revoked_at` track use, and the raw key is shown once by `Agent.create_with_key()`.
- **Policy / MerchantRule** (`apps/policies`): a policy is versioned (a new row per edit) and holds currency, minor-unit caps/budgets/threshold, merchant mode, velocity, payee cooldown, untrusted-source action, injection threshold, classifier requirement, approval TTL, and timezone. Constraints require the threshold to be at or below the cap and the injection threshold to be 0–100. Merchant rules are unique per policy.
- **Payee** (`apps/payees`): the known destination for a merchant (type, value, SHA-256 fingerprint, trusted time, status), unique per organization and merchant.
- **SpendRequest** (`apps/spend`, UUID id): agent, policy reference and `policy_version` snapshot, `idempotency_key`, `request_hash`, amount in minor units and currency, merchant, payee and destination snapshot, purpose, provenance (`source_type`/`source_ref`), capped evidence excerpt plus hash, `risk_score`, an immutable `decision`, a forward-only `status`, reasons, matched rules, PayPal reference/status, and decided/executed times.
- **Approval** (`apps/approvals`, one per spend request): outcome (pending, approved, denied, expired), approver, note, `requested_at`, `expires_at`, `decided_at`.
- **AuditEvent** (`apps/audit`): event type, organization, agent, spend request, actor type/id, JSON payload, `prev_hash`/`hash`, created time. Append-only in code: `save()` on an existing row and `delete()` raise `PermissionError`. Create events with `AuditEvent.record(...)`. Each event hashes a canonical envelope (event metadata plus canonical JSON, no floats, UTC ISO timestamps with microseconds), links to the previous event, and serializes writers with the organization row lock. `python manage.py verify_audit` recomputes the chain. The admin shows events read-only, and a PostgreSQL trigger blocks direct UPDATE/DELETE/TRUNCATE.
- **WebhookEvent** (`apps/payments`): deduplicated PayPal inbox (`paypal_event_id` unique), event type, payload, signature-verified flag, received/processed times.

Money is stored as integer minor units with an ISO-4217 code (zero-decimal currencies such as JPY handled), converted to decimal strings only at the API and PayPal boundaries.

Note: bulk operations like `QuerySet.update()` bypass model methods. Never use them on audit events; the database trigger is the backstop.

## 5. API (planned unless marked built)

- `GET /healthz` (built): liveness, no database access
- `GET /readyz` (built): readiness, checks the database connection
- `GET /api/health/` (built): compatibility alias for liveness
- `GET /api/schema/` and `/api/docs/` (built): OpenAPI schema and Swagger UI
- `POST /v1/spend-requests/` (built): submit a request with an `Idempotency-Key`. Returns 201 with `decision` (allow, deny or needs_approval), reasons and matched rules in the body
- `GET /v1/spend-requests/{id}/` (built): read one of the agent's own requests
- `GET /v1/approvals/` and `GET /v1/approvals/{id}/` (built): approver/admin queue, pending by default, paginated
- `POST /v1/approvals/{id}/approve` and `/deny` (built): approve rechecks current policy and destination; a failed recheck returns 409 and leaves the request pending
- `GET /v1/policies/` (built): policy versions and merchant rules for the caller's organizations; policy writes are still planned
- `GET /v1/audit/` and `GET /v1/audit/verify/` (built): filterable log and admin-only chain verification
- `POST /webhooks/paypal`: payment events (planned)

The OpenAPI schema is generated with drf-spectacular and used to generate the SDK.

### Dashboard authentication and approval API (built)

- Dashboard endpoints use Django session authentication; agents cannot use their API keys on approval, policy, or audit endpoints. A same-origin dashboard can log in through `/api-auth/login/` or the admin.
- Roles come from `OrgMembership`: `admin` and `approver` may read and decide approvals, `viewer` may read policies and audit, and only `admin` may verify audit chains. Results are always scoped to the caller's organizations.
- Approvals are pending by default (`?outcome=all` includes decided rows) and use `limit`/`offset` pagination. Double approve/deny is idempotent; a conflicting decision returns 409.
- Approval locks follow the same order: agent, current policy, spend request, approval, then organization for audit. The recheck re-runs the current policy and budget. If a hard rule now denies or a known payee fingerprint changed, the API returns 409 with rule ids and leaves the approval pending.
- An overdue approval is marked expired on decision and by `python manage.py expire_approvals`; run that command from cron (every minute is sufficient). The command is idempotent.
- `GET /v1/audit/verify/` verifies only the organizations where the caller is an admin and returns 409 at the first broken event.

### Agent authentication and the spend request API (built)

- Agents authenticate with `Authorization: Bearer <agent key>`. Keys look like `agk_...`. Lookup is by the stored prefix, then a constant-time hash comparison; suspended agents and revoked keys are rejected.
- Create an agent, its policy and merchant rules with `python manage.py create_agent NAME [--org ORG] --allow acme.com --block evil.com --cap 100 --threshold 50 --daily 500 --weekly 2000 --monthly 5000`. The key is printed once.
- `POST /v1/spend-requests/` requires `Idempotency-Key` (1–255 printable characters) and takes `amount`, `currency`, `merchant`, optional `purpose`, `source_ref`, `evidence_excerpt`, `source`, and a paired `destination_type`/`destination_value`. Source values are `trusted`, `untrusted`, `web_page`, `email`, `invoice`, `tool_output` or `unknown`; missing means `untrusted`. Unknown body fields are rejected with 400. The response is HTTP 201 for every decision, so agents and SDKs must read `decision`, never just the status code.
- Replaying the same key and body returns the stored request with `Idempotent-Replayed: true`; reusing the key with a different body or destination returns 409. The hash includes the normalized destination.
- Writes are throttled per agent key (`THROTTLE_AGENT`, default 60/min), and request bodies over 64 KiB are rejected.
- Budgets count requests that are approved, executing, or succeeded. Denied requests and pending approvals do not count, so a pending approval never reserves budget; approval rechecks before executing. R16 uses the current ISO week starting Monday. R08 velocity and R09 merchant-window use the same budget statuses over the rolling `velocity_window_seconds` window; R09 reuses that window and counts only the normalized merchant.
- Accepted requests with a destination upsert the organization merchant `Payee`; a later request that changes the fingerprint makes older pending approvals fail the destination recheck.
- The agent row is locked first (`select_for_update`), then the current policy row is locked, then the spend request is written, and only then does the audit append lock the organization. Every spend path uses that order, and approval decisions take the same locks in the same order. Concurrent requests for one agent therefore serialize and cannot both pass a budget. SQLite ignores the locks; PostgreSQL enforces them, a 20-way concurrency test covers the budget, and a query-order test covers agent-before-policy locking.
- Audit events written per request: `request.received`, `decision.made`, and `approval.requested` when a human is needed.
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

    cd backend && source venv/bin/activate && ruff check . && lint-imports && python manage.py test
    cd frontend && npm run lint && npm run build

GitHub Actions runs the same checks on every push and pull request, with the backend job running against a PostgreSQL 17 service container (`DATABASE_URL`), so the budget row lock is exercised for real. Every rule in the policy engine gets a unit test. Lint settings live in `backend/ruff.toml` (generated migrations are excluded; RUF012 is ignored because Django's `Meta` and admin options are plain class attributes). Keeping the config in the repo makes local runs and CI identical.

## 10. Deployment (planned)

- Contabo VPS runs Caddy (TLS/reverse proxy), gunicorn web workers and the Procrastinate worker; PostgreSQL 17 is managed Neon in `eu-central-1`.
- Use the direct Neon URL for migrations and the worker (LISTEN/NOTIFY does not work through a transaction pooler). Use the pooled URL for web only if it is tested with server-side cursors disabled.
- Keep an off-server `pg_dump` of the audit tables; Neon backup retention depends on the plan. On the free tier, disable scale-to-zero before a demo to avoid cold starts.
- Production settings (`config.settings.prod`) require `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`, force `DEBUG=False`, set secure cookies, HSTS without preload, and exempt `/healthz` and `/readyz` from the HTTPS redirect. Run `python manage.py createcachetable` once for the database throttle cache.
- Configuration comes from the environment (one server-side env file), never the repo.
- PayPal webhooks need a public HTTPS hostname, and the demo URL must open without a login. Keep `/admin/` off the public route or behind an IP allowlist.
- Demo resets create a fresh demo agent and suspend the previous one; nothing is deleted, and a `demo.reset` audit event is appended.

## 11. Decisions log

- **Django over Spring Boot**: the PayPal AI Toolkit supports Python and TypeScript, so the agent layer lives inside the Django service as one backend.
- **Deterministic rules over model judgment**: limits cannot be argued away by text.
- **SQLite for local tests, PostgreSQL 17 for CI and production via `DATABASE_URL`**: Neon provides managed backups; SQLite keeps the default test run fast and offline. The budget lock (`select_for_update`) only works on PostgreSQL.
- **Python env named `venv`** inside `backend/`.
- **Money as integer minor units**: avoids float/decimal drift and handles zero-decimal currencies; converted at the API and PayPal boundaries.
- **Versioned policies**: editing a policy inserts a new version so a spend request can record the rules actually in force.
- **Custom `accounts.User`**: set before the first real migration so organization membership and roles can be added without a later user-model swap.
- **Keys in their own table**: rotation, `last_used_at`, and `revoked_at` without touching the agent row.
- **SSH to GitHub over port 443**: some networks block port 22.
- **API keys are stored hashed**: only a prefix and SHA-256 hash are kept, so a database leak does not expose agent keys.
- **Audit log is append-only and hash-chained per organization**, blocked by model code and, on PostgreSQL, by a database trigger; agents are created through `Agent.create_with_key()` rather than the admin.
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
- [x] Data models, migrations and admin (split into accounts, agents, policies, payees, spend, approvals, payments, audit)
- [x] Rule engine (pure function, unit-tested)
- [x] Spend request API with agent key auth and audit trail
- [x] Framework-free `engine/` package with R01–R10, R13, R14 and R16
- [x] R08 velocity, R09 merchant-window and R16 weekly-budget rules
- [x] Idempotent spend requests, agent-row locking, audit hash chain and demo reset command
- [x] Approval queue API with recheck, session auth, roles, and expiry command
- [x] Read APIs for policies and audit, plus admin audit verification
- [ ] PayPal sandbox payment execution and webhooks
- [ ] Demo agent and injection classifier
- [ ] Dashboard screens
- [ ] Deploy on the Contabo VPS
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
