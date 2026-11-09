# AGT-004: Registration and Organization Onboarding

**Ticket ID:** AGT-004
**Title:** Registration with organization onboarding via backend services
**Objective:** Implement registration flow that collects organization details and creates Organization + OrgMembership through backend services, never trusting frontend-supplied role.
**Status:** Done
**Assigned owner:** Isaac (backend) + Del (frontend)

## Context
Delarum's RegisterPage collects `full_name`, `organization`, and `accept_terms`. The task requires: if registration collects organization details, implement the correct association through backend services. Never trust a frontend-supplied role or organization identifier without backend authorization.

## Scope
- CustomAccountAdapter.save_user creates AccountProfile with full_name
- If organization name provided in signup, create Organization and OrgMembership (role: ADMIN for creator)
- Organization name validated and deduplicated (get_or_create)
- No role escalation through registration (creator gets ADMIN in their org only)
- Frontend RegisterPage sends full_name, organization, accept_terms to signup endpoint

## Acceptance Criteria
- Signup creates User + AccountProfile + Organization + OrgMembership
- Organization name is deduplicated (same name → same Organization)
- Creator gets ADMIN role in their organization
- No profile data used as authorization source
- Existing users without profile get one on first profile access (get_or_create)

## Dependencies
- AGT-001 (AccountProfile)

## Files affected
- `backend/apps/accounts/adapters.py` (save_user override)
- `frontend/src/pages/RegisterPage.tsx` (signup payload)
- `frontend/src/api/auth.ts` (signUp function)

## Required tests
- Signup with organization creates Organization + OrgMembership
- Signup without organization creates User + Profile only
- Duplicate organization name reuses existing Organization
- Creator has ADMIN role in their organization

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- Backend signup flow creates correct domain objects
- Frontend registration page submits all required fields