# AGT-010: CI/CD and Deployment Verification

**Ticket ID:** AGT-010
**Title:** CI/CD pipeline and deployment verification
**Objective:** Verify CI passes on the integration branch and deployment is reproducible.
**Status:** In Progress
**Assigned owner:** Winstone (DevOps/technical lead)

## Context
CI runs backend tests (Django + PostgreSQL + Redis) and frontend (lint + build). The integration branch must pass all CI checks before review.

## Evidence Produced
- `docs/deployment/CI_CD_VERIFICATION.md` — CI/CD pipeline documentation
- Local CI reproduction verified: ruff check, Django check, makemigrations --check, tests (694 pass), frontend tsc/lint/build all pass
- `.github/workflows/ci.yml` exists with backend, frontend, and deployment-config jobs

## Blocker
Deployment automation not yet enabled. VPS SSH access not established. See AGT-012.

## Scope
- Backend CI: ruff check, lint-imports, manage.py check, spectacular validate, makemigrations --check, manage.py test
- Frontend CI: npm ci, npm run lint, npm run build
- Deployment: Docker compose, environment variables, secret management

## Acceptance Criteria
- CI backend job passes (PostgreSQL 17 service container)
- CI frontend job passes
- `makemigrations --check --dry-run` reports no changes
- Docker compose builds and runs
- `.env.example` has placeholder values (no real secrets)

## Dependencies
- AGT-001 through AGT-006 (integration complete)

## Files affected
- `.github/workflows/ci.yml` (if changes needed)
- `backend/requirements.txt` (if new deps)
- `frontend/package.json` (if new deps)

## Required tests
- Full CI pipeline passes on integration branch

## Definition of done
- CI passes on `integration/agentgate-dashboard` branch
- Deployment verified (docker compose up)