# AgentGate Core Backend — Contabo Deployment Guide

**Task:** AG-06 — Deployment Foundation
**Branch:** `intergration`
**Status:** Infrastructure files implemented. VPS/DNS/Neon provisioning still manual.

This guide covers deploying the AgentGate **core backend** (Django + Gunicorn + Procrastinate worker + Redis + Caddy) to a Contabo VPS. PayPal is intentionally excluded.

---

## 1. VPS Prerequisites

- Contabo VPS (Ubuntu 22.04/24.04 LTS recommended).
- At least 2 vCPU, 4 GB RAM, 40 GB disk.
- SSH access with key-based authentication.
- A public IPv4 (and optionally IPv6).
- Docker Engine 24+ and Docker Compose v2.

## 2. DNS and Hostname Setup

1. Create an A record: `app.example.com` → VPS public IP.
2. (Optional) AAAA record for IPv6.
3. Wait for propagation before enabling HTTPS.
4. Set `DOMAIN=app.example.com` in `.env.production`.

## 3. Docker Installation

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in
docker --version && docker compose version
```

## 4. Production Environment Configuration

```bash
cd /opt/agentgate
cp .env.production.example .env.production
# Edit .env.production with real values (see section 5)
chmod 600 .env.production
```

## 5. Secret Generation and Safe Transfer

Generate secrets on a trusted machine (never commit them):

```bash
# Django secret key
python -c "import secrets; print(secrets.token_urlsafe(50))"

# MFA encryption key (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Redis password
python -c "import secrets; print(secrets.token_urlsafe(32))"

# MFA bypass code
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Transfer `.env.production` via `scp` or a secrets manager. Never email or commit it.

## 6. Building and Starting Services

```bash
# Build the image
docker compose build
# Compose reads variables from .env.production via env_file in compose.yaml.
# No --env-file flag is required.

# Start Redis first (dependency)
docker compose up -d redis

# Start web + worker + Caddy
docker compose up -d

# Check status
docker compose ps
```

## 7. Running Deployment Checks

```bash
# Django system checks (production)
docker compose exec web python manage.py check --deploy --settings=config.settings.prod

# Health endpoints
curl -fsS https://app.example.com/healthz
curl -fsS https://app.example.com/readyz
```

## 8. Running Migrations (controlled one-off)

**Migrations are a deliberate release operation, NOT run automatically by replicas.**

```bash
# One-off migration container (same image, no replica conflicts)
docker compose run --rm web python manage.py migrate

# Create cache table (once)
docker compose run --rm web python manage.py createcachetable

# Collect static (already done by entrypoint, but can be forced)
docker compose run --rm web python manage.py collectstatic --noinput
```

## 9. HTTPS Verification

- Caddy provisions certificates automatically via Let's Encrypt.
- Verify: `curl -vI https://app.example.com` (check TLS, HSTS header).
- Check Caddy logs: `docker compose logs caddy`.

## 10. Health Checks

- Container health: `docker compose ps` (shows healthy/unhealthy).
- Application: `GET /healthz` (200), `GET /readyz` (200 if DB connected).
- Worker: monitor logs (`docker compose logs worker`); no HTTP endpoint.

## 11. Log Inspection

```bash
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f caddy
docker compose logs -f redis
```

## 12. Backup and Restore

See `DATABASE_BACKUP_AND_RECOVERY.md` for the full backup, restore and disaster-recovery procedure.

### Backup (daily cron recommended)

```bash
# From a trusted host with DB access
pg_dump "$DATABASE_URL" --format=custom --file=agentgate-$(date +%F).dump
```

### Restore

```bash
pg_restore --dbname="$DATABASE_URL" agentgate-YYYY-MM-DD.dump
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py verify_audit
```

## 13. Updating and Rolling Back Releases

### Update

```bash
git pull origin intergration
docker compose build
# Compose reads variables from .env.production via env_file in compose.yaml.
# No --env-file flag is required.
docker compose run --rm web python manage.py migrate
docker compose up -d
```

### Rollback

```bash
git checkout <previous-commit>
docker compose build
# Compose reads variables from .env.production via env_file in compose.yaml.
# No --env-file flag is required.
docker compose up -d
# Restore DB from backup if migrations were applied
```

## 14. Firewall and SSH Recommendations

- UFW: allow 22 (or 443 for SSH), 80, 443. Deny all else.
- SSH: key-only auth, disable password, non-root deploy user.
- Fail2ban for SSH brute-force protection.
- Redis and PostgreSQL NOT exposed to the host or public.



## 17. Docker network architecture (AG-10)

Two networks are defined in `compose.yaml`:

- **edge** — Caddy + Django web. Caddy forwards HTTPS requests to `web:8000`.
  Redis and the worker are NOT members.
- **backend** — Django web + Procrastinate worker + Redis. Django and the worker
  access Redis and retain outbound connectivity to Neon (PostgreSQL). The
  backend network is NOT marked `internal: true` so outbound internet access
  (Neon) remains available.

Django web is the only service on both networks, acting as the bridge between
public traffic and internal services. Redis is not exposed to the host and is
only reachable from web and worker on the backend network. Only Caddy publishes
ports 80 and 443.

## 15. Common Failure Diagnosis

| Symptom | Likely cause | Fix |
|---|---|---|
| Web container unhealthy | Missing env var (fail-fast) | Check `docker compose logs web` |
| 502 from Caddy | Web not ready | Wait or check web logs |
| `/readyz` returns 503 | DB connection failed | Verify `DATABASE_URL`, network, SSL |
| Worker not processing | Wrong queue name | Queues are fixed to `smoke,approvals,payments,audit` in compose.yaml; verify the worker command |
| HTTPS cert not issued | DNS not propagated | Wait, check Caddy logs |
| Static files 404 | collectstatic not run | Run `docker compose run --rm web python manage.py collectstatic --noinput` |

---

## Implemented vs. Manual

**Implemented (in repo):**
- `Dockerfile` (Python 3.13, non-root, Gunicorn)
- `compose.yaml` (Caddy, web, worker, Redis)
- `deploy/Caddyfile` (auto-HTTPS, static serving)
- `deploy/entrypoint.sh` (collectstatic)
- `.env.production.example` (all required vars)
- `.dockerignore` (excludes secrets, venv, etc.)
- `docs/deployment/CONTABO_DEPLOYMENT.md` (this file)

**Still requires manual provisioning:**
- VPS, DNS, Neon database, Docker installation
- Secret generation and transfer
- Firewall/SSH hardening
- Backup cron setup
- Monitoring/alerting

---

**PayPal exclusion:** This deployment is based on `intergration`, which contains no PayPal routes, services, or configuration. PayPal sandbox remains a separate local development environment on `feat/paypal-sandbox`. Do not add PayPal credentials or configuration to this deployment.

**STOP. Awaiting Tech Lead review.**
filePath">
/home/winst/agent-gate/.kilo/worktrees/intergration/docs/deployment/CONTABO_DEPLOYMENT.md
## 16. Redis role and eviction (AG-07 review)

- Redis is used as Django's cache backend only (`CACHES["default"] = RedisCache`).
- Background jobs (Procrastinate) are stored in PostgreSQL, NOT Redis.
- Therefore `allkeys-lru` eviction with a 256 MB cap affects only cache entries, never queued jobs.
- Redis persistence (AOF) is enabled for cache durability across restarts.
- Redis is not published to the host and is password-protected.


## 18. CI validation (AG-12)

GitHub Actions job `deployment-config` (in `.github/workflows/ci.yml`) validates the deployment foundation on every push and pull request:

1. Checks out the repository.
2. Creates a placeholder `.env.production` from `.env.production.example` (no real secrets).
3. Runs `docker compose --env-file .env.production config --quiet`.
4. Runs static Python assertions on `compose.yaml` (services, networks, membership, ports, no PayPal).
5. Builds the core backend Docker image (`docker build -t agentgate-web:ci .`).
6. Removes the placeholder `.env.production` (runs even on failure).

### What CI validates
- Compose YAML validity and service/network/volume/port topology.
- AG-10 network segmentation (edge/backend, dual-homed web).
- Only Caddy publishes ports 80/443.
- Dockerfile builds successfully (dependencies install, image assembles).

### What CI does NOT validate
- Actual container startup or health checks (no Docker daemon runtime in CI build step beyond build).
- Neon connectivity (no database provisioned).
- Caddy certificate provisioning (requires real DNS).
- End-to-end request flow.
- Backup/restore procedures.

### Reproducing locally
```bash
cp .env.production.example .env.production
# fill placeholders (or use sed replacements as in CI)
docker compose --env-file .env.production config --quiet
python3 -c "import yaml; print(yaml.safe_load(open('compose.yaml'))['services'].keys())"
docker build -t agentgate-web:local .
rm -f .env.production
```

A successful image build does not prove the stack works against Neon or a real domain. Runtime verification on a VPS is still required.
