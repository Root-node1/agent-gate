# AGT-011: Presentation Readiness

**Ticket ID:** AGT-011
**Title:** Presentation readiness verification
**Objective:** Verify the application demonstrates a coherent user journey for the presentation.
**Status:** In Progress
**Assigned owner:** Ian (UX/product presenter), Winstone (release verification)

## Context
The presentation requires a working, coherent application. The checklist must distinguish completed features from prototypes and planned functionality. No faked functionality.

## Evidence Produced
- `docs/presentation/GAMMA_SLIDE_CONTENT.md` — 12-slide Gamma presentation content
- `docs/presentation/DEMO_RUNBOOK.md` — 10-step demo script with fallback plan
- `docs/presentation/PRESENTATION_READINESS.md` — Feature readiness classification

## Blocker
Demo cannot be verified against real backend until VPS deployment is complete (blocked by AGT-012).

## Scope
Presentation verification checklist:
1. Register a user (with organization)
2. Authenticate (login)
3. Restore an existing session (refresh page, still logged in)
4. View the dashboard
5. View and update the profile
6. Demonstrate organization association
7. Demonstrate role-based access (admin/approver/viewer)
8. Demonstrate MFA (if configured)
9. Log out
10. Demonstrate a blocked unauthorized request

## Acceptance Criteria
- All 10 checklist items demonstrated successfully
- Each item marked as completed feature (not prototype/planned)
- No faked or mocked functionality in the demo
- Demo works against real backend

## Dependencies
- AGT-001 through AGT-009 (all integration complete)

## Files affected
- Presentation verification checklist (document)
- Demo data/setup scripts (if needed)

## Required tests
- Manual walkthrough of all 10 checklist items
- Backend and frontend both running

## Definition of done
- All 10 presentation checklist items verified
- Demo script documented
- Known limitations documented