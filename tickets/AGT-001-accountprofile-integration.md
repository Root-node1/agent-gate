# AGT-001: AccountProfile Integration

**Ticket ID:** AGT-001
**Title:** Integrate AccountProfile linked to accounts.User
**Objective:** Add Delarum's AccountProfile functionality as a one-to-one extension of accounts.User, preserving our custom user model as the source of identity.
**Status:** Done
**Assigned owner:** Isaac (backend)

## Context
Delarum's `origin/feat/dashboard` branch implements `AccountProfile` in the `gate` app with `full_name`, `organization` (CharField), and `terms_accepted_at`. Our backend retires the `gate` app and uses domain applications (`accounts.User`, `Organization`, `OrgMembership`). The AccountProfile must not duplicate authentication fields, organization membership, or authorization data.

## Scope
- Add `AccountProfile` model to `apps/accounts/models.py` with `user` (OneToOne to User) and `full_name` only
- Create migration `apps/accounts/migrations/0002_accountprofile.py`
- Add `AccountProfileSerializer` and include `profile` in `CurrentUserSerializer`
- Add `ProfileView` (GET/PATCH) at `/api/auth/profile/`
- Update `CustomAccountAdapter.save_user` to create profile on signup
- Register `AccountProfile` in admin

## Acceptance Criteria
- `AccountProfile` model exists with `user` OneToOne and `full_name` CharField
- Migration `0002_accountprofile.py` created and `makemigrations --check` passes
- `GET /api/auth/profile/` returns profile for authenticated user
- `PATCH /api/auth/profile/` updates `full_name` only
- Profile auto-created on user signup via adapter
- Organization membership NOT stored on profile (uses Organization + OrgMembership)
- All 57 existing auth tests pass

## Dependencies
- accounts.User custom model (already exists)
- Organization + OrgMembership models (already exist)

## Files affected
- `backend/apps/accounts/models.py`
- `backend/apps/accounts/migrations/0002_accountprofile.py`
- `backend/apps/accounts/serializers.py`
- `backend/apps/accounts/views.py`
- `backend/apps/accounts/urls.py`
- `backend/apps/accounts/adapters.py`
- `backend/apps/accounts/admin.py`

## Required tests
- Profile creation on signup
- Profile retrieval via GET /api/auth/profile/
- Profile update via PATCH /api/auth/profile/
- Missing profile handled gracefully (get_or_create)

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- Django `check` passes
- `makemigrations --check --dry-run` reports no changes
- All existing auth tests pass