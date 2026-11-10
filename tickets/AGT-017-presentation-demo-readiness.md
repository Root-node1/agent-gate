# AGT-017: Presentation and Demonstration Readiness

**Ticket ID:** AGT-017
**Title:** Finalize presentation and demonstration for 10 November 2026
**Objective:** Prepare Gamma slide content, demo runbook, and verified feature status for the team presentation.
**Priority:** High (deadline: tomorrow)
**Status:** In Progress
**Assigned owner:** Ian + Winstone

## Context
Presentation documentation has been created (`docs/presentation/GAMMA_SLIDE_CONTENT.md`, `docs/presentation/DEMO_RUNBOOK.md`, `docs/presentation/PRESENTATION_READINESS.md`). Demo must be verified against real backend where possible, with honest status for blocked features.

## Scope
- Verify slide content accuracy against implementation
- Ensure architecture diagram matches implementation
- Document deployment status honestly
- Create demo account instructions
- Test demonstration sequence
- Document backup demonstration
- Document limitations
- Ensure no unverified functionality is presented as complete
- Classify every feature: VERIFIED / PARTIAL / IMPLEMENTED — NOT E2E VERIFIED / BLOCKED / NOT IMPLEMENTED

## Acceptance Criteria
- Slide content is accurate and evidence-backed
- Architecture diagram matches implementation
- Deployment status is honest
- Demo account instructions exist
- Demonstration sequence tested where possible
- Limitations documented
- No unverified functionality presented as complete
- Feature readiness classification complete

## Dependencies
- AGT-013 (VPS deployment for live demo)
- AGT-016 (Tauri build for desktop demo)

## Files/modules
- `docs/presentation/GAMMA_SLIDE_CONTENT.md`
- `docs/presentation/DEMO_RUNBOOK.md`
- `docs/presentation/PRESENTATION_READINESS.md`

## Testing
- Manual walkthrough of demo steps where backend is available
- Verify each slide claim against code/documentation evidence

## Definition of Done
- All 12 slides accurate and evidence-backed
- Demo runbook tested against available backend
- Feature readiness classification published
- Limitations clearly documented

## Notes
- I (user) will create the actual Gamma slides myself
- Do not invent adoption, performance, or customer metrics
- Demo must distinguish: Verified / Implemented but not E2E verified / Blocked / Not implemented