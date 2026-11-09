# AgentGate — VPS Deployment Guide

**Branch:** `integration/agentgate-dashboard`
**Baseline:** `origin/main` at `0f247755589630ea34b7c79785e3f44eca468746`
**Status:** Pilot / team testing environment (not production-certified)
**PayPal:** Excluded (PayPal sandbox remains on `feat/paypal-sandbox`)

---

## 1. Architecture Overview

AgentGate deploys as a Docker Compose stack on a single Contabo VPS:

| Service | Image | Role | Published Ports |
|---|---|---|---|
| caddy | `caddy:2-alpine` | Reverse proxy, auto-HTTPS (Let's Encrypt), static file serving | 80, 443 |
| web | `agentgate-web:latest` | Django + Gunicorn (app server) | None (internal only) |
| worker | `agentgate-web:latest` | Procrastinate background job worker | None (internal only) |
| redis | `redis:7-alpine` | Django cache backend (password-protected, AOF) | None (internal only) |

**Network segmentation:**
- `edge` network: Caddy ↔ web only (public-facing).
- `backend` network: web ↔ worker ↔ Redis + outbound to Neon PostgreSQL.
- Only Caddy publishes ports to the host. Django (8000) and Redis (6379) are internal-only.

**Database:** Neon PostgreSQL (external managed service, not containerized).

---

## 2. VPS Access — REQUIRED INPUT

SSH access to the VPS could not be established from this environment:

| Item | Observed Value | Status |
|---|---|---|
| Host | `vps.zindika.app` (194.163.174.37) | DNS resolves ✅ |
| Ping | Responds ✅ | Host is up |
| SSH port 22 | Connection timed out ❌ | SSH not reachable on port 22 |
| SSH config (`~/.ssh/config`) | `Host contabo` → `vps.zindika.app`, User `winstone`, Key `~/.ssh/contabo_ed25519` | Config exists ✅ |

**Required from you:**
1. The correct SSH port (if not 22).
2. Confirmation that the `winstone` user and `contabo_ed25519` key are valid on this VPS.
3. Whether SSH key-based authentication is enabled and password auth is disabled.

Do not share private keys or passwords. Provide only host, port, and username.

---

## 3. Prerequisites (on the VPS)

| Item | Minimum | Notes |
|---|---|---|
| OS | Ubuntu 22.04 or 24.04 LTS | |
| CPU | 2 vCPU | |
| RAM | 4 GB | |
| Disk | 40 GB | SSD recommended |
| Docker Engine | 24+ | |
| Docker Compose | v2 | |
| SSH | Key-based, non-root user | |
| Firewall (UFW) | Allow 22 (SSH), 80, 443; deny all else | |
| DNS | A record: `app.example.com` → VPS IP | Required for HTTPS |

---

## 4. Deployment Steps

### 4.1 Prepare the VPS

```bash
# SSH into the VPS
ssh contabo

# Install Docker and Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group membership
docker --version && docker compose version

# Configure firewall (UFW)
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 4.2 Deploy the Application

```bash
# Clone the repository
git clone git@github.com:Root-node1/agent-gate.git /opt/agentgate
cd /opt/agentgate
git checkout integration/agentgate-dashboard

# Copy production environment template
cp .env.production.example .env.production
chmod 600 .env.production

# Edit .env.production with real values (see Section 5)
# Never commit .env.production
```

### 4.3 Generate Secrets (on a trusted machine, not the VPS)

```bash
# Django secret key
python -c "import secrets; print(secrets.token_urlsafe(50))"

# MFA encryption key (Fernet) — REQUIRED, fail-closed if missing
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Redis password
python -c "import secrets; print(secrets.token_urlsafe(32))"

# MFA bypass code (emergency only)
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Transfer `.env.production` via `scp` or a secrets manager. Never email or commit it.

### 4.4 Configure DNS

Create an A record: `app.example.com` → VPS public IP. Wait for propagation before starting Caddy (needed for Let's Encrypt certificate issuance).

### 4.5 Build and Start

```bash
cd /opt/agentgate

# Build the Docker image
docker compose build

# Start Redis first (dependency for web and worker)
docker compose up -d redis

# Start web, worker, and Caddy
docker compose up -d

# Check status
docker compose ps
```

### 4.6 Run Migrations (one-off, controlled)

```bash
# Migrations are a deliberate release operation
docker compose run --rm web python manage.py migrate

# Collect static files (also done by entrypoint)
docker compose run --rm web python manage.py collectstatic --noinput
```

### 4.7 Run Deployment Checks

```bash
# Django system checks (production)
docker compose exec web python manage.py check --deploy --settings=config.settings.prod

# Health endpoints
curl -fsS https://app.example.com/healthz
curl -fsS https://app.example.com/readyz
```

---

## 5. Required Environment Variables (`.env.production`)

| Variable | Required | Description | Example |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Yes | `config.settings.prod` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Yes | Django signing key | Random 50+ char string |
| `DJANGO_DEBUG` | Yes | Must be `False` | `False` |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated hostnames | `app.example.com` |
| `TRUSTED_PROXY_COUNT` | Yes | Proxy count for Caddy | `1` |
| `DJANGO_ADMIN_PATH` | Yes | Custom admin URL path | `agentgate-admin/` |
| `DATABASE_URL` | Yes | Neon PostgreSQL direct URL | `postgresql://...` |
| `REDIS_PASSWORD` | Yes | Redis access password | Random string |
| `REDIS_URL` | Yes | Redis connection URL | `redis://:pass@redis:6379/0` |
| `MFA_ENCRYPTION_KEY` | Yes | Fernet key for MFA secrets | `Fernet.generate_key().decode()` |
| `MFA_ENCRYPTION_PREVIOUS_KEYS` | No | Older Fernet keys for rotation | Comma-separated |
| `MFA_BYPASS_CODE` | Yes | Emergency MFA bypass | Random string |
| `CSRF_TRUSTED_ORIGINS` | Yes | Origins allowed for CSRF | `https://app.example.com` |
| `SECURE_HSTS_SECONDS` | No | HSTS max-age | `31536000` |
| `FRONTEND_ORIGIN` | Yes | Frontend origin for allauth links | `https://app.example.com` |
| `DOMAIN` | Yes | Caddy domain for TLS | `app.example.com` |
| `GUNICORN_WORKERS` | No | Gunicorn worker count | `2` |
| `GUNICORN_TIMEOUT` | No | Gunicorn timeout (seconds) | `60` |
| `PROCRASTINATE_WORKER_CONCURRENCY` | No | Worker concurrency | `1` |
| `PAYMENT_EXECUTOR` | No | Payment executor | `fake` |
| `PAYMENTS_EXECUTION_ENABLED` | No | Enable payment execution | `false` |

**Never commit `.env.production`.** It contains secrets.

---

## 6. Team Access Instructions

### 6.1 Backend Base URL

After deployment, the backend is accessible at:
```
https://app.example.com
```

Health check endpoints:
- `GET https://app.example.com/healthz` → `{"status": "ok"}` (200)
- `GET https://app.example.com/readyz` → 200 if DB connected, 503 otherwise

### 6.2 Frontend API Configuration

The frontend connects to the backend at `/api` and `/v1` paths. For local development:

```bash
# In frontend/vite.config.ts (dev only — already configured)
proxy: {
  '/api': 'http://127.0.0.1:8000',
  '/v1': 'http://127.0.0.1:8000',
}
```

For the deployed environment, the frontend is served by Caddy at the same origin as the backend, so no CORS configuration is needed for the web dashboard.

For the Tauri desktop app, the `tauri.conf.json` CSP `connect-src` must include the deployed backend URL.

### 6.3 CORS and CSRF

- **CORS:** The web dashboard is served from the same origin as the backend (via Caddy), so no CORS headers are needed for browser access.
- **CSRF_TRUSTED_ORIGINS:** Must include `https://app.example.com` (and any desktop app origin if applicable).
- **Session cookies:** `SameSite=Lax`, `Secure=True`, `HttpOnly=True`.
- **CSRF cookie:** `SameSite=Lax`, `Secure=True`, `HttpOnly=False` (SPA reads it via JavaScript).

### 6.4 Access Control

| Access | Who | How |
|---|---|---|
| VPS SSH | Team members | Individual SSH keys, non-root user |
| Django Admin | Admin only | Custom path (`DJANGO_ADMIN_PATH`), restricted |
| PostgreSQL | Internal only | Not published to host or public internet |
| Redis | Internal only | Not published to host, password-protected |
| Backend API | Team members | Via `https://app.example.com` |

### 6.5 Revoking Access

- Remove the user's SSH key from `~/.ssh/authorized_keys` on the VPS.
- Rotate `DJANGO_SECRET_KEY` and `MFA_ENCRYPTION_KEY` if a key may be compromised.
- Revoke all API keys via the admin interface.
- Force password resets for affected accounts.

---

## 7. Rollback Procedure

```bash
cd /opt/agentgate

# Roll back to previous commit
git checkout <previous-commit>

# Rebuild and restart
docker compose build
docker compose run --rm web python manage.py migrate
docker compose up -d

# If migrations were applied and need reverting:
# Restore database from backup (see BACKUP_AND_RESTORE.md)
```

---

## 8. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Web container unhealthy | Missing env var (fail-fast) | `docker compose logs web` |
| 502 from Caddy | Web not ready | Wait, check web logs |
| `/readyz` returns 503 | DB connection failed | Verify `DATABASE_URL`, Neon connectivity |
| Worker not processing | Queue config | Queues fixed to `smoke,approvals,payments` |
| HTTPS cert not issued | DNS not propagated | Wait, check Caddy logs |
| Static files 404 | collectstatic not run | `docker compose run --rm web python manage.py collectstatic --noinput` |
| MFA_ENCRYPTION_KEY missing | App won't start | Set `MFA_ENCRYPTION_KEY` in `.env.production` |

---

## 9. Production-Readiness Assessment

| Area | Status | Notes |
|---|---|---|
| Container security (non-root user) | ✅ | `agentgate` user |
| Network segmentation | ✅ | Edge/backend networks |
| Internal-only DB/Redis | ✅ | Not published to host |
| Auto-HTTPS (Caddy + Let's Encrypt) | ✅ | Automatic certificate provisioning |
| Security headers | ✅ | HSTS, X-Frame-Options, nosniff |
| Session/CSRF cookies | ✅ | Secure, HttpOnly, SameSite=Lax |
| MFA encryption key | ⚠️ | Must be configured (`MFA_ENCRYPTION_KEY`) |
| Secrets management | ⚠️ | `.env.production` on VPS filesystem |
| Backup automation | ❌ | Not yet implemented (see BACKUP_AND_RESTORE.md) |
| Monitoring/alerting | ❌ | Not yet implemented |
| Code signing (desktop) | ❌ | Not yet configured |

**Verdict:** Suitable for controlled team testing/pilot. Not yet production-certified pending backup automation, monitoring, and security review (AGT-007/AGT-008).