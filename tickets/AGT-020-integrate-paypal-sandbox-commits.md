# AGT-020: Integrate PayPal Sandbox Commits from feat/paypal-sandbox into Integration Branch

**Ticket ID:** AGT-020
**Title:** Review and integrate 19 PayPal sandbox commits from feat/paypal-sandbox into integration/agentgate-dashboard
**Objective:** Review all 19 PayPal sandbox commits on feat/paypal-sandbox that are not yet in integration/agentgate-dashboard, and selectively integrate approved ones via pull requests.
**Priority:** High (blocks payments demo and team testing)
**Status:** Not started
**Assigned owner:** Isaac (backend), with Anthony (security review)

## Context

`feat/paypal-sandbox` is at `b1a0ee2` with 19 commits not present in `origin/integration/agentgate-dashboard` (`f6ad730`). These commits implement the complete PayPal sandbox integration: webhook ingestion, payout submission, checkout capture/order creation, OAuth HTTP client, financial reconciliation, denied capture handling, and sandbox feature configuration. This work is not yet on any remote-tracking branch (only a local branch exists).

## Commit inventory (19 commits)

| SHA | Subject | Area |
|-----|---------|------|
| 50dd3e9 | Add sandbox-only PayPal feature configuration | Payments config |
| ca9c46c | Add checkout domain and operation records | Payments data model |
| 79fb34d | Add sandbox PayPal OAuth HTTP client | Payments client |
| 1326b34 | Verify sandbox client and API hostname | Payments client |
| 28969c7 | Add sandbox checkout order creation | Payments checkout |
| b017bbc | Add sandbox checkout capture | Payments checkout |
| c7fc185 | Preserve uncertain checkout capture states | Payments checkout |
| ccfc896 | Add durable payout authorization | Payments payout |
| fbbc477 | Add sandbox payout submission | Payments payout |
| 01736c2 | Harden payout reservation concurrency | Payments payout |
| c748c32 | Harden sandbox payout submission safety | Payments payout |
| d229e2d | Correct payout financial state classification | Payments payout |
| 3fb440e | Add verified sandbox webhook ingestion | Payments webhooks |
| 59f9090 | Harden webhook ingestion reliability | Payments webhooks |
| 9551622 | Process verified sandbox webhooks | Payments webhooks |
| 396af99 | Harden webhook financial reconciliation | Payments reconciliation |
| b5271b3 | Test webhook financial reconciliation safety | Payments reconciliation |
| b1f992b | Verify denied captures before webhook transition | Payments reconciliation |
| b1a0ee2 | Prepare isolated PayPal sandbox environment | Payments docs |

## Scope

- Review each commit's diff for correctness, financial safety, and no unintended behavior changes
- Anthony must review all payment security aspects: webhook signature verification, financial reconciliation, denied capture handling, payout authorization
- Verify no PayPal credentials or secrets are committed
- Verify frontend TypeScript, lint, and build pass if frontend changes included
- Verify backend tests pass
- Create PRs into `integration/agentgate-dashboard` for approved commits
- Do not force-push; do not discard either side's work

## Acceptance Criteria

- All 19 commits reviewed and dispositioned (approve / reject / request changes)
- Anthony signs off on all payment security aspects
- No PayPal credentials or secrets committed
- Backend tests pass (0 failures)
- Frontend TypeScript, lint, and build pass (if frontend changes)
- Approved commits merged into `integration/agentgate-dashboard` via PR

## Dependencies

- AGT-007 security assessment (Anthony should review payment security findings)
- AGT-008 security remediation (may be needed before integration)

## Files affected

- `backend/apps/payments/` (webhooks, payouts, checkout, OAuth client, reconciliation)
- `backend/apps/spend/services.py` (if payment integration touches spend pipeline)
- `backend/apps/policies/` (if merchant mode/payee handling included)
- `.env.production.example` (if PayPal sandbox config added)
- `backend/.env.example` (if PayPal sandbox config added)
- Frontend payment-related files (if any)

## Required tests

- All 694 existing backend tests pass
- New payment tests included with commits pass
- Webhook signature verification tests pass
- Financial reconciliation tests pass
- Denied capture handling tests pass
- Frontend build/lint/type check pass (if frontend changes)

## Definition of done

- All 19 commits reviewed and dispositioned
- Anthony signs off on payment security
- Approved commits merged into `integration/agentgate-dashboard` via PR
- No secrets committed
