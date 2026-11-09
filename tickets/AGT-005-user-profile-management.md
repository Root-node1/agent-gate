# AGT-005: User Profile Management

**Ticket ID:** AGT-005
**Title:** User profile retrieval and update endpoint
**Objective:** Provide GET/PATCH /api/auth/profile/ for reading and updating the authenticated user's display profile.
**Status:** Done
**Assigned owner:** Isaac (backend) + Del (frontend)

## Context
AccountProfile holds `full_name` only. Organization membership is managed through Organization + OrgMembership, never through the profile. Users can only edit their own profile's `full_name`.

## Scope
- ProfileView GET returns AccountProfileSerializer data
- ProfileView PATCH updates `full_name` only (validated by serializer)
- get_or_create pattern ensures profile always exists
- CurrentUserSerializer includes `profile` field
- Profile data never changes application roles or authorization

## Acceptance Criteria
- GET /api/auth/profile/ returns { full_name }
- PATCH /api/auth/profile/ with { full_name } updates profile
- PATCH only accepts full_name (read_only_fields = ["user"])
- Profile auto-created if missing (get_or_create)
- Unauthenticated requests return 401

## Dependencies
- AGT-001 (AccountProfile model)

## Files affected
- `backend/apps/accounts/views.py` (ProfileView)
- `backend/apps/accounts/urls.py` (profile URL)
- `backend/apps/accounts/serializers.py` (AccountProfileSerializer, CurrentUserSerializer)

## Required tests
- Profile retrieval for authenticated user
- Profile update (full_name only)
- Profile auto-creation on first access
- Unauthenticated access returns 401
- Cannot update read-only user field

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- Profile endpoint tested and working