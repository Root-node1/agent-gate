# AgentGate — Contabo VPS and Coolify Deployment Guide

This document defines the deployment architecture, VPS provisioning checklist,
Coolify configuration, and step-by-step procedures for deploying AgentGate
onto a Contabo VPS managed by Coolify.

**Do not purchase VPS resources, change DNS, or deploy to production without
the founder's explicit approval.**

---

## 1. Architecture Overview

The production deployment stack:

| Container | Role | Public? | Persistent storage |
|---|---|---|---|
| `caddy` | TLS + reverse proxy + static files | Yes (80, 443) | `caddy_data`, `staticfiles` (read) |
| `web` | Django / Gunicorn (2–4 workers) | No (internal only) | `staticfiles` (write) |
| `worker` | Procrastinate background jobs | No | None |
| `redis` | Cache + rate-limiting | No | `redis_data` |
| PostgreSQL 17 | Authoritative data | No | External managed or Coolify DB |

The frontend React SPA is compiled to `staticfiles` by the Dockerfile's
`collectstatic` step and served directly by Caddy — no Node.js process runs
in production.

---

## 2. Contabo VPS Sizing

### Minimum specification

Based on the actual memory profile of this stack:

| Component | Estimated RAM |
|---|---|
| Django / Gunicorn (2 workers) | 300–500 MB |
| Procrastinate worker | 150–300 MB |
| Redis 7 (256 MB maxmemory) | ~260 MB |
| Coolify orchestrator + Traefik | 600–900 MB |
| OS baseline | 300–500 MB |
| **Total working set** | **~2.5–3.5 GB** |

**Recommended minimum:** Contabo **Cloud VPS M** (4 vCPU, 8 GB RAM, 100 GB NVMe SSD).

A 4 GB VPS is the absolute floor; 8 GB gives headroom for PostgreSQL if
running it on the same host, peak traffic, and backup execution.

If PostgreSQL is managed externally (Neon, Supabase, AWS RDS), a 4 vCPU /
4 GB RAM VPS may suffice, but verify during load testing.

### Disk

- 50 GB NVMe: adequate for application code, Redis data, Caddy certs, and
  moderate backup staging.
- 100 GB NVMe: recommended if PostgreSQL also runs on the same host.
- Do not run the VPS below 20% free disk — pg_dump staging and log rotation
  both require headroom.

---

## 3. VPS Provisioning Checklist

Perform these steps before installing Coolify:

```bash
# 1. Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# 2. Create a non-root deployment user
sudo adduser deployer
sudo usermod -aG sudo deployer

# 3. Configure SSH key authentication
# (copy your public key to /home/deployer/.ssh/authorized_keys)
# Then in /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
sudo systemctl reload ssh

# 4. Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH (or your custom port)
sudo ufw allow 80/tcp     # HTTP (ACME challenge + redirect)
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 8000/tcp   # Coolify Web UI — restrict to your IP if possible
sudo ufw enable

# 5. Add swap (4 GB recommended)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 6. Install Docker Engine (official Docker repository)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deployer

# 7. Install Coolify
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash
```

After Coolify installs, open `https://<vps-ip>:8000` to complete the
Coolify initial setup (admin user, SSH key import).

---

## 4. Coolify Deployment Strategy

### Recommended: Deploy the existing Docker Compose stack

Coolify supports deploying a repository's `compose.yaml` directly as a
Docker Compose application.

1. In Coolify → **New Resource** → **Docker Compose**.
2. Connect the GitHub repository (`Root-node1/agent-gate`).
3. Set the branch to `release/v0.1.0-ux-demo` (confirm with founder
   before changing).
4. Set the **Compose file path** to `compose.yaml`.
5. Enter all required environment variables (see Section 5).
6. Enable **auto-deploy on push** only after the branch is confirmed stable.

**Note on PostgreSQL:** The `compose.yaml` does not include a PostgreSQL
service (by design — it uses `DATABASE_URL` to point at an external instance).
You must either:

- Use **Coolify → New Resource → PostgreSQL** to provision a managed PostgreSQL 17
  instance inside Coolify, then set `DATABASE_URL` to its internal connection string.
- Use an external managed PostgreSQL provider (Neon, Supabase, AWS RDS) and set
  `DATABASE_URL` to that connection string.

**Do not run PostgreSQL 18 or SQLite in production.** The Procrastinate migration
requires PostgreSQL 17.

### Database migrations

The `deploy/entrypoint.sh` runs `collectstatic` only. Migrations must be run
manually before the first deployment, or added to the entrypoint:

```bash
# Either add to entrypoint.sh (safe — migrations are idempotent):
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"

# Or run once after deployment from a one-off container:
docker compose exec web python manage.py migrate --noinput
```

**Approval required before modifying `deploy/entrypoint.sh`.**

---

## 5. Environment Variables

Copy `.env.production.example` to `.env.production` on the VPS (or add each
variable in Coolify's environment UI). Never commit `.env.production`.

Required minimum for production start:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<50+ char random string>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com
TRUSTED_PROXY_COUNT=1
DOMAIN=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
FRONTEND_ORIGIN=https://your-domain.com
SECURE_HSTS_SECONDS=31536000

DATABASE_URL=postgresql://user:password@host:5432/agentgate?sslmode=require
REDIS_PASSWORD=<strong random password>
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

MFA_ENCRYPTION_KEY=<Fernet key — generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

PAYMENT_EXECUTOR=fake
PAYMENTS_EXECUTION_ENABLED=false
WEBHOOK_RETENTION_DAYS=30

GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=60
```

For PayPal execution (after Sandbox sign-off):

```bash
PAYMENT_EXECUTOR=paypal
PAYMENTS_EXECUTION_ENABLED=true
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<sandbox client id>
PAYPAL_CLIENT_SECRET=<sandbox client secret>
PAYPAL_WEBHOOK_ID=<webhook id from PayPal Developer Dashboard>
```

For email delivery (required for password reset / verification):

```bash
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_HOST_USER=<mailgun user>
EMAIL_HOST_PASSWORD=<mailgun password>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=AgentGate <no-reply@your-domain.com>
```

---

## 6. Caddy Configuration

The `deploy/Caddyfile` uses `{$DOMAIN}` from the environment:

```caddyfile
{$DOMAIN:localhost} {
    handle_path /static/* {
        root * /srv/static
        file_server
    }
    reverse_proxy web:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-For {remote_host}
    }
    encode gzip zstd
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
}
```

Caddy automatically provisions and renews a Let's Encrypt TLS certificate for
`DOMAIN`. Ensure DNS A record points to the Contabo VPS IP before first
deployment so ACME challenges succeed.

---

## 7. Persistent Volume Management

Volumes defined in `compose.yaml`:

| Volume | Contents | Backup required? |
|---|---|---|
| `redis_data` | Cache + ephemeral rate-limit state | No (disposable on restart) |
| `caddy_data` | Let's Encrypt TLS certificates + Caddy config cache | No (auto-renewed) |
| `caddy_config` | Runtime Caddy config | No |
| `staticfiles` | Compiled frontend assets + Django collected statics | No (rebuilt on deploy) |

PostgreSQL data is **not in a Docker volume** — it lives in the managed
database or external instance. Back it up via `pg_dump` as described in
`BACKUP_AND_DISASTER_RECOVERY.md`.

---

## 8. Health Checks

| Service | Check | Endpoint | Expected |
|---|---|---|---|
| `web` | HTTP GET | `http://127.0.0.1:8000/healthz` | 200 `{"status": "ok"}` |
| `web` (readiness) | HTTP GET | `http://127.0.0.1:8000/readyz` | 200 (checks DB connection) |
| `caddy` | Caddy admin API | `http://127.0.0.1:2019/config/` | 200 |
| `redis` | `redis-cli ping` | internal | `PONG` |
| `worker` | No HTTP endpoint | — | Monitor via logs |

---

## 9. Deployment Sequence (First Deploy)

**Requires founder approval before execution.**

```bash
# 1. On the Contabo VPS, as the deployer user:
git clone https://github.com/Root-node1/agent-gate.git
cd agent-gate
git checkout release/v0.1.0-ux-demo

# 2. Create .env.production from the example (fill in real values):
cp .env.production.example .env.production
nano .env.production  # fill in every required variable

# 3. Build the image:
docker compose build

# 4. Run migrations (before first start):
docker compose run --rm web python manage.py migrate --noinput

# 5. Create a superuser for the Django admin (optional):
docker compose run --rm web python manage.py createsuperuser

# 6. Start all services:
docker compose up -d

# 7. Verify health:
curl -f http://localhost/healthz
docker compose ps
docker compose logs web --tail=50
```

---

## 10. Redeployment (Subsequent Deploys)

```bash
cd agent-gate
git pull origin release/v0.1.0-ux-demo
docker compose build
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --no-deps web worker
docker compose logs web --tail=50
```

---

## 11. Coolify Domain and HTTPS Configuration

In Coolify:

1. Go to the application → **Settings → Domains**.
2. Add `https://your-domain.com`.
3. Enable **Force HTTPS** and **Generate SSL certificate** (Let's Encrypt).
4. Set the **port** to `443` (Caddy handles TLS internally).
5. Ensure the DNS A record for `your-domain.com` points to the VPS public IP.

If using Coolify's own Traefik proxy instead of the Caddy container, update
`compose.yaml` to remove the `caddy` service and add appropriate Coolify
labels — this requires reviewing the current Coolify documentation before
modifying. The existing Caddy approach is compatible with Coolify's
"bring your own proxy" mode.

---

## 12. Monitoring and Log Rotation

```bash
# View live logs:
docker compose logs -f web
docker compose logs -f worker

# Log rotation (add to /etc/logrotate.d/docker):
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    missingok
    notifempty
    copytruncate
}

# Monitor disk usage:
df -h
docker system df
```

Set up email alerts for disk usage > 80% and failed health checks before
going live.
