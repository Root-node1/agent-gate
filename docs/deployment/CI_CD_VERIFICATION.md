# AgentGate — CI/CD Verification

**Branch:** `integration/agentgate-dashboard`
**Status:** CI pipeline exists; deployment automation not yet enabled

---

## 1. Existing CI Pipeline (`.github/workflows/ci.yml`)

The repository has a GitHub Actions CI workflow that validates:

### 1.1 Backend CI Job

| Step | Description | Status |
|---|---|---|
| Checkout repository | `actions/checkout@v4` | ✅ |
| Set up Python | Python 3.13 | ✅ |
| Install dependencies | `pip install -r backend/requirements.txt` | ✅ |
| Django check | `python manage.py check` | ✅ |
| Migration check | `python manage.py makemigrations --check --dry-run` | ✅ |
| Ruff lint | `ruff check .` | ✅ |
| Run tests | `python manage.py test` | ✅ |
| Docker build | `docker build -t agentgate-web:ci .` | ✅ |

### 1.2 Frontend CI Job

| Step | Description | Status |
|---|---|---|
| Checkout repository | `actions/checkout@v4` | ✅ |
| Set up Node.js | Node 20+ | ✅ |
| Install dependencies | `npm ci` | ✅ |
| TypeScript check | `npx tsc --noEmit` | ✅ |
| ESLint | `npm run lint` | ✅ |
| Production build | `npm run build` | ✅ |

### 1.3 Deployment Config Validation Job

Validates `compose.yaml` and Dockerfile build (from `CONTABO_DEPLOYMENT.md` §18):
- Compose YAML validity and service/network/volume/port topology
- Network segmentation (edge/backend)
- Only Caddy publishes ports 80/443
- Dockerfile builds successfully

---

## 2. Local CI Reproduction

```bash
# Backend
cd /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard/backend
python manage.py check
python manage.py makemigrations --check --dry-run
ruff check .
python manage.py test

# Frontend
cd /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard/frontend
npx tsc --noEmit
npm run lint
npm run build

# Docker
docker compose --env-file .env.production config --quiet
docker build -t agentgate-web:local .
```

---

## 3. Deployment Automation

**Status:** Not automated. Manual deployment via Docker Compose on VPS.

**Recommended (future):**
- GitHub Actions deployment job triggered on tag push or manual dispatch
- Build and push Docker image to container registry
- SSH into VPS, pull image, restart services
- Run migrations one-off before restart

**Not recommended (without approval):** Automatic deployment to production on every push to `main`.

---

## 4. Environment Configuration for CI

CI creates a placeholder `.env.production` from `.env.production.example` (no real secrets) for compose validation. Real secrets are injected at deployment time via the VPS filesystem or secrets manager.

---

## 5. Deployment Failure Handling

| Failure | Detection | Response |
|---|---|---|
| Container unhealthy | `docker compose ps` | Check `docker compose logs web` |
| Migration failure | `docker compose run --rm web python manage.py migrate` exits non-zero | Roll back to previous commit |
| Health check failure | `/healthz` or `/readyz` returns non-200 | Investigate logs, roll back if needed |
| Build failure | CI job fails | Fix and re-push; do not deploy |

---

## 6. Required Before Deployment Automation

| Item | Status |
|---|---|
| VPS SSH access confirmed | ⏳ Pending (port 22 timed out) |
| Secrets injected securely | ⏳ Pending |
| Backup automation deployed | ⏳ Pending |
| Security review (AGT-007/008) complete | ⏳ Pending |
| E2E tests pass against deployed env | ⏳ Pending |