# AGT-013: Contabo VPS Backend Deployment

**Ticket ID:** AGT-013
**Title:** Deploy Django backend to Contabo VPS using Docker Compose
**Objective:** Deploy the existing AgentGate backend on the Contabo VPS using the existing Docker Compose architecture.
**Priority:** High (blocks team access and E2E testing)
**Status:** Blocked (waiting on AGT-012 VPS access)
**Assigned owner:** Winstone, with Isaac supporting backend issues

## Context
The integration branch `integration/agentgate-dashboard` contains complete Docker Compose deployment files: `compose.yaml`, `Dockerfile`, `deploy/Caddyfile`, `deploy/entrypoint.sh`, `.env.production.example`. The backend must be deployed to `vps.zindika.app` for team testing and presentation.

## Scope
- Verify deployment architecture (Caddy + Django/Gunicorn + Procrastinate worker + Redis + Neon PostgreSQL)
- Document production environment variables from `.env.production.example`
- Handle secrets securely (never commit `.env.production`)
- Configure Caddy with HTTPS (Let's Encrypt auto-provisioning)
- Start Django web service
- Start Procrastinate worker
- Verify Redis connectivity
- Verify Neon PostgreSQL connectivity
- Apply migrations safely (one-off, controlled)
- Verify `/healthz` responds successfully
- Verify `/readyz` confirms dependency readiness
- Verify logs accessible
- Document rollback procedure

## Acceptance Criteria
- Deployment architecture verified against existing compose.yaml
- Production environment variables documented
- Secrets handled securely (`.env.production` never committed)
- Caddy and HTTPS configured
- Django service starts and is healthy
- Worker starts
- Redis works
- Neon PostgreSQL connectivity verified
- Migrations applied safely
- `/healthz` responds successfully (200)
- `/readyz` confirms dependency readiness (200)
- Logs accessible via `docker compose logs`
- Rollback procedure documented

## Dependencies
- AGT-012 (VPS SSH access must be established first)

## Files/modules
- `compose.yaml`
- `Dockerfile`
- `deploy/Caddyfile`
- `deploy/entrypoint.sh`
- `.env.production.example`
- `backend/config/settings/prod.py`

## Testing
- `docker compose ps` — all services healthy
- `curl -fsS https://<domain>/healthz` — returns 200
- `curl -fsS https://<domain>/readyz` — returns 200
- `docker compose logs web` — no errors
- `docker compose exec web python manage.py check --deploy --settings=config.settings.prod` — passes

## Definition of Done
- Backend deployed and accessible via HTTPS
- Health endpoints verified
- Rollback procedure documented
- No production credentials committed to repository

## Notes
- Do not claim deployment success before external verification
- Do not replace Neon database with local PostgreSQL unless documented technical reason
- Never expose Redis or PostgreSQL publicly
- Never overwrite existing server data without explicit approval
- PayPal sandbox intentionally excluded (separate branch)