# AgentGate — UX Demo Handoff

## Ready-to-send message

> Hello,
>
> Here are everything you need to run the AgentGate local demo.
>
> **Repository:**  
> `https://github.com/Root-node1/agent-gate.git`  
> Branch: `release/v0.1.0-ux-demo`
> (Please confirm with me that this is still the correct demo branch before cloning.)
>
> **What AgentGate does:**  
> AgentGate is a spend-control firewall between AI agents and PayPal. It enforces
> deterministic rules (caps, budgets, merchant lists, approval thresholds) before
> anything reaches a payment provider. The built-in dashboard demo runs entirely
> in your browser — no PayPal account or API keys are required to run the UI demo.
>
> **To start the demo:**  
> 1. Follow the [local setup guide](LOCAL_SETUP.md). You will need Git, Python 3.13,
>    Node.js 22, and either Docker (recommended) or PostgreSQL 17 installed locally.
> 2. Register a local account; the email verification code appears in the backend terminal.
> 3. Follow the [demo walkthrough](DEMO_WALKTHROUGH.md) for a 10–15 minute guided tour.
>
> **Demo data:**  
> The dashboard loads sample scenarios (agents, policies, payments, approvals, audit)
> entirely in browser memory. No database setup or seed command is needed for the UI demo.
> Reloading the page resets the sample data.
>
> **What is simulated vs. real:**
> - Policy decisions, approvals, payment outcomes, and audit events in the dashboard
>   are **browser-memory simulation only**. They are not backend records.
> - The backend authentication (login, email verification, password reset, MFA) is
>   **real** and requires the Django backend to be running.
> - The "Live API tester" page sends requests to the actual backend; its payment
>   executor defaults to `fake` (no PayPal calls).
> - No PayPal operations are performed during the UI demo.
>
> **PayPal AI Toolkit (optional — not required for the UI demo):**  
> The [PayPal AI Toolkit](https://github.com/paypal/AI-Toolkit) is a developer workflow
> plugin for certain AI coding agents. It is completely separate from the AgentGate
> runtime and is not needed to run the dashboard demo. If you want to use it, you will
> need your own PayPal Developer sandbox account. See [PAYPAL_AI_TOOLKIT_SETUP.md](PAYPAL_AI_TOOLKIT_SETUP.md).
>
> The toolkit currently documents these agents: **Claude Code, OpenAI Codex, Cursor,
> and IBM Bob**. Please tell me which AI coding agent you use before following
> agent-specific steps — VS Code GitHub Copilot is not an established supported host
> for this toolkit.
>
> **Credential rules (important):**
> - Do not share passwords, verification codes, MFA recovery codes, PayPal client
>   secrets, or MCP access tokens in chat, screenshots, or logs.
> - The UI demo does not need any PayPal credentials. Do not configure
>   `PAYPAL_CLIENT_ID` or `PAYPAL_CLIENT_SECRET` in `backend/.env` for the demo.
> - Use only sandbox/test credentials — never live PayPal credentials or real
>   customer data.
>
> **Reporting issues:**  
> If setup fails, reply with the non-sensitive error message and the step you were on.
> Do not include `.env` contents, session cookies, passwords, or credentials.
>
> **Known limitations:**  
> Browser authentication journeys (login, signup, MFA, password reset) have been
> verified by automated backend and frontend tests but have not yet been confirmed
> in a live browser session. See [DEMO_READINESS.md](DEMO_READINESS.md) for the
> precise status of each area.
>
> Let me know if you have any questions.

---

## Context notes (for the founder / sender of this message)

**Before sending, confirm:**

- [ ] The branch `release/v0.1.0-ux-demo` is still the intended demo target.
- [ ] The UX person knows which AI coding agent they use (affects Toolkit instructions).
- [ ] You have not added real PayPal credentials or live mode to the demo branch.
- [ ] You have reviewed `DEMO_READINESS.md` and are comfortable with its stated limitations.

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
