# AGT-015: Team VPS Access and Environment Setup

**Ticket ID:** AGT-015
**Title:** Configure team access to shared VPS testing environment
**Objective:** Allow the development team to use the shared VPS testing environment safely with documented access and revocation procedures.
**Priority:** High (required for team testing)
**Status:** Not started
**Assigned owner:** Winstone

## Context
After VPS deployment (AGT-013), team members need controlled access to the backend. Access must be documented, CORS/CSRF configured for intended origins, and admin/database access restricted.

## Scope
- Document backend base URL
- Document frontend API configuration
- Configure CORS for intended origins only
- Configure CSRF trusted origins correctly
- Ensure database not publicly exposed
- Restrict administrative access
- Create team onboarding instructions
- Manage SSH access individually where appropriate
- Document access revocation procedure

## Acceptance Criteria
- Backend base URL documented
- Frontend API configuration documented
- CORS and CSRF configured for intended origins only
- Database not publicly exposed
- Administrative access restricted (custom admin path, limited users)
- Team onboarding instructions created
- SSH access managed individually
- Revocation procedure documented

## Dependencies
- AGT-013 (VPS backend deployment must be complete first)

## Files/modules
- `docs/deployment/VPS_DEPLOYMENT.md`
- `backend/config/settings/prod.py` (CSRF_TRUSTED_ORIGINS, ALLOWED_HOSTS)

## Testing
- Backend accessible at documented URL
- `/healthz` returns 200 from team member's network
- Database port not accessible from public internet
- Admin path not guessable/default

## Definition of Done
- Team can access backend with documented credentials
- Access revocation procedure tested
- No public exposure of database or Redis

## Notes
- Do not share VPS root account
- Use individual SSH accounts or controlled access mechanism
- Do not expose PostgreSQL publicly
- Document how access is revoked