# Guided Demo Walkthrough

Estimated time: 10–15 minutes.

**Before starting:**
- Complete [local setup](LOCAL_SETUP.md), register a local account, and verify
  your email using the code in the backend terminal.
- Use sandbox/demo data only. Never enter real payment details or credentials.
- All policy decisions, approvals, payment results, and audit events in the
  dashboard are **browser-memory simulation** — they are not backend records
  and reset on page reload.

---

## Presenter Script

### Opening (1 minute)

> "AgentGate is a spend-control firewall between an AI agent and a payment
> provider. As AI systems get access to payment authority, they become targets
> for prompt injection — where a hidden instruction in a web page or invoice
> tells the agent to override its limits and pay an attacker's link.
>
> AgentGate's core idea is simple: *deterministic rules, not models, decide
> whether a payment happens.* An AI classifier may advise on risk, but it
> cannot override a hard rule or bypass required approval. Every decision is
> written to an audit log."

---

## Step-by-Step Walkthrough

| Step | Action | Narration | What it actually demonstrates |
|---|---|---|---|
| **1. Landing page** | Open `/` | "The landing page shows the three outcomes: allow, deny, and needs approval. The animated diagram illustrates how a request flows through the firewall." | Public product overview. No backend request or PayPal call. |
| **2. Register / sign in** | Click **Get started** or open `/register`. Enter email and password. Enter the 6-digit code from the backend terminal. Sign in. | "This account is local to this demo. Email verification is required — it is not bypassed even for demos." | Real backend authentication. Email code printed to backend terminal. |
| **3. Dashboard overview** | Open `/app` | "The overview shows sample agents, recent activity, and spending totals. This is sample data loaded in browser memory — it resets on reload." | Browser-memory seed data. Not backend records. |
| **4. Policies** | Click **Policies** in the sidebar. Open an agent's policy. | "These limits — per-transaction cap, daily/monthly budget, merchant allow/block list, approval threshold — are what the policy engine enforces deterministically. A model never changes these values." | Policy structure display. Demo edits are in-memory. |
| **5. Allowed payment** | Click **Simulate a request** in the sidebar. The form defaults to a $45 GitHub payment. Click **Run this request**. | "This passes all sample rules: within the per-transaction cap, within budget, trusted provenance, and on the allow list. The demo grants it and creates a simulated payment reference." | Client-side policy simulation. No backend request, no PayPal call. |
| **6. Denied payment** | Click **Over a hard limit** scenario. Click **Run this request**. | "The amount exceeds the sample per-transaction cap. The engine returns DENY and the simulated payment is never sent. Notice the rule code — R05_PER_TX_CAP — appears in the result." | Hard-rule enforcement. No payment attempted. |
| **7. Needs-approval payment** | Click **A suspicious invoice** scenario. Click **Run this request**. | "The amount is within the cap, but the source is flagged as untrusted — a prompt injected by the web page, not the user. The engine escalates to human approval and holds the payment." | Approval-escalation rule (R13 / R10). No PayPal call. |
| **8. Approval queue** | Click **Review in approval queue** (or navigate to **Approvals**). Open the pending item. | "The approver sees the request details, the agent that sent it, the rule that triggered escalation, and the risk indicators. The request has not been sent to PayPal." | Approval detail view. Demo state only. |
| **9. Approve a payment** | In the approval detail, click **Approve**. Add an optional note. Confirm. | "The approver clicks Approve. In the full backend flow, this authorizes the payment executor. In this demo, the payment result is simulated — no PayPal call is made." | Approval action. The dashboard shows a simulated "completed" payment result. |
| **10. Deny a payment** | (Optional) Reset and repeat step 7. Click **Deny** instead. | "Deny records the decision and prevents any future payment for this request. No PayPal call was made." | Denial flow. |
| **11. Audit log** | Click **Audit log** in the sidebar. | "Every decision — received, decided, approval requested, approval outcome, payment result — appears in the audit timeline. In the production backend, this log is append-only and hash-chained so it cannot be altered." | Browser-memory demo audit events. The real backend log is append-only and PostgreSQL-backed. |
| **12. Security settings** | Click **Settings** → **Security** tab. Enter your password and click **Unlock**. | "Security settings are backed by real server-side MFA. The enrollment and removal flows call the allauth TOTP API." | Real backend integration. MFA enrollment browser journey still needs manual verification — see DEMO_READINESS.md. |
| **13. PayPal settings** | Click **Settings** → **PayPal** tab. | "The connection shows 'Sandbox · demo mode'. Live payments are off. The backend executor defaults to fake, so no PayPal calls are made in this demo." | Correctly labeled status. No real connection. |
| **14. Sign out** | Click the sign-out icon or use **Sign out** in the account menu. | "Logout calls the server-side allauth session deletion endpoint. The session is invalidated on the backend." | Real backend logout. |

---

## Key Messages to Reinforce

**Determinism first:**  
> "The model's advisory score contributes to the displayed risk rating, but it
> cannot override a hard rule or bypass required approval. If the rule says DENY,
> the payment is blocked — regardless of what the AI thinks."

**What is simulated vs. real:**  
> "The dashboard demo is entirely in browser memory. The approval, the payment
> reference, the audit events — these are sample data to illustrate the UX. The
> backend policy engine, approval enforcement, and audit trail are real and have
> full test coverage. The PayPal integration uses the Sandbox API and defaults to
> a fake executor for demos."

**AI safety:**  
> "AgentGate reduces the attack surface for prompt injection. It is not a complete
> defence — paraphrases and novel attacks can still get through. The goal is to
> make deterministic rules, not models, the last word on whether money moves."

---

## If a Step Fails

- Do not bypass email verification, MFA, or CSRF as a workaround.
- Record the browser console error and the non-sensitive error message.
- Follow [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- Do not capture passwords, codes, secrets, or recovery codes in screenshots.

---

## Optional: Live API Tester

**Requires:** Backend running, an AgentGate agent API key (from `python manage.py seed_demo`).

The **Live API tester** (`/app/live`) sends a real request to the backend policy engine.
The decision it shows is a real policy evaluation — not simulated. The payment executor
defaults to `fake` unless `PAYMENT_EXECUTOR=paypal` and `PAYMENTS_EXECUTION_ENABLED=true`
are explicitly configured.

Label the result clearly: "This is a real backend decision; the payment is not sent to PayPal."

Steps:

1. Run `python manage.py seed_demo` from `backend/`.
2. Copy the printed API key.
3. Open `/app/live`, paste the key, and fill in the request form.
4. Click **Submit**.
5. The decision card shows the backend's response with rule codes.
