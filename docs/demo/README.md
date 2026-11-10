# AgentGate UX Demo

AgentGate is a spend-control firewall between AI agents and PayPal.
Deterministic policy rules decide whether a payment request is allowed, denied,
or held for human approval. An AI classifier is advisory and cannot override
the rules. Every decision is recorded in an append-only audit log.

---

## Documents in this folder

| Document | Purpose |
|---|---|
| [LOCAL_SETUP.md](LOCAL_SETUP.md) | Clone the repo, configure PostgreSQL 17, start the app |
| [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) | 10–15 minute guided tour with presenter script |
| [PAYPAL_AI_TOOLKIT_SETUP.md](PAYPAL_AI_TOOLKIT_SETUP.md) | PayPal AI Toolkit for coding agents (optional) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and fixes |
| [DEMO_READINESS.md](DEMO_READINESS.md) | Verification status of every demo area |
| [UX_HANDOFF.md](UX_HANDOFF.md) | Ready-to-send message for the UX person |

---

## Quick start

1. Follow [LOCAL_SETUP.md](LOCAL_SETUP.md) to start the application.
2. Register a local account; verify with the code printed in the backend terminal.
3. Follow [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

---

## What is simulated vs. real

| Feature | Type | Notes |
|---|---|---|
| Policy decisions in dashboard | Browser-memory simulation | Resets on reload; no backend call |
| Approval actions in dashboard | Browser-memory simulation | Resets on reload; no backend call |
| Payment results in dashboard | Browser-memory simulation | Resets on reload; no PayPal call |
| Audit log in dashboard | Browser-memory simulation | In-memory demo events |
| Backend login / session / MFA | Real — requires Django backend | Backend auth (allauth) |
| Email verification / password reset | Real — requires Django backend | Code printed in backend terminal |
| Live API tester request | Real — backend policy engine | Payment executor = fake by default |
| PayPal Sandbox payments | Real — requires credentials | Requires explicit configuration |

---

## Requirements

- Git
- Python 3.13+
- Node.js 22+
- PostgreSQL 17 (or Docker to run the isolated PG17 container)
- No PayPal account needed for the UI demo
- No MCP server or AI coding agent needed for the UI demo

---

## Credential rules

- Never share passwords, verification codes, MFA recovery codes, PayPal
  client secrets, or MCP access tokens in chat, screenshots, or logs.
- The UI demo does not need PayPal credentials — do not add them to `backend/.env`.
- Use only sandbox/test credentials — never live credentials or real customer data.

---

## Branch

The current UX demo targets: `release/v0.1.0-ux-demo`  
HEAD: `fbe9323c0d4411dfcccf51760bfbf7fac33b4202`

Confirm the correct branch with the maintainer before cloning.
PR #15 is closed and was not merged.
