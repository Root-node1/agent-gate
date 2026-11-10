# Local AgentGate Setup

Requirements: Python 3.13+, Node.js 22+, PostgreSQL 17 (or Docker).

PostgreSQL 17 is mandatory — do not substitute SQLite or PostgreSQL 18.
The Procrastinate background job migration uses PostgreSQL-only SQL
(`CREATE EXTENSION`) and cannot run on SQLite.

---

## 1. Start a PostgreSQL 17 database

### Option A: Docker (recommended — no host PostgreSQL installation needed)

The command below binds only to loopback (`127.0.0.1`) and uses a fresh,
temporary container. The password is a local-only example; never reuse it.

```bash
docker run --rm -d --name agentgate-demo-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17

# Wait for readiness (up to 60 s)
for attempt in $(seq 1 30); do
  docker exec agentgate-demo-pg17 pg_isready -U agentgate -d agentgate \
    >/dev/null 2>&1 && break
  sleep 2
done

# Verify: should print "17.x" (not 18.x)
docker exec agentgate-demo-pg17 psql -U agentgate -d agentgate \
  -Atc 'SHOW server_version;'

export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
```

Stop the container when done (`docker stop agentgate-demo-pg17`).
Because the container uses `--rm`, data is discarded on stop. Restart with
the same command to get a fresh database.

### Option B: Host-installed PostgreSQL 17

If PostgreSQL 17 is already installed separately, check the version at the
explicit host and port you plan to use:

```bash
psql -h 127.0.0.1 -p 5432 -U postgres -Atc 'SHOW server_version;'
```

The output must start with `17.` — not 18 or 16. If the host has another
PostgreSQL version on the default port, do not use that port.

Create the database and role:

```bash
psql -h 127.0.0.1 -p 5432 -U postgres <<SQL
CREATE ROLE agentgate WITH LOGIN PASSWORD 'agentgate-local-only';
CREATE DATABASE agentgate OWNER agentgate;
SQL

export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:5432/agentgate'
```

---

## 2. Clone the repository

The current UX demo targets `release/v0.1.0-ux-demo`. Confirm
the branch with the maintainer before cloning:

```bash
git clone https://github.com/Root-node1/agent-gate.git
cd agent-gate
```

If you already have a clone, check out the correct branch:

```bash
git fetch origin
git checkout release/v0.1.0-ux-demo
```

---

## 3. Configure and start the application

`run.sh` handles:
- Creating the Python virtual environment (first run).
- Installing Python dependencies (first run).
- Creating `backend/.env` with a fresh development secret key (first run,
  if the file is absent).
- Installing Node.js frontend dependencies (first run).
- Applying database migrations.
- Starting the Django dev server on `:8000` and the Vite dev server on `:5173`.

```bash
# DATABASE_URL must be set before run.sh (or in backend/.env)
export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
./run.sh
```

For repeat starts, either export `DATABASE_URL` again in the shell or add
it to `backend/.env`. Do not overwrite an existing `.env`.

**Development defaults (do not change for the UI demo):**

- `DJANGO_DEBUG=True` — development only.
- Email: Django console backend. Verification and reset emails appear in the
  backend terminal as plain text. Do not configure SMTP for the demo.
- `PAYMENT_EXECUTOR=fake` — no PayPal calls. Do not add PayPal credentials.
- `MFA_ENCRYPTION_KEY` is not required for basic email/password signup. TOTP
  enrollment will show a warning until a Fernet key is set (see below).

---

## 4. Optional: Configure MFA encryption key

TOTP enrollment requires `MFA_ENCRYPTION_KEY`. Generate a local key and
add it to `backend/.env`:

```bash
backend/venv/bin/python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the output to `backend/.env`:

```
MFA_ENCRYPTION_KEY=<paste the generated key here>
```

Stop and restart `./run.sh` after changing `.env`. Keep the key private;
do not reuse it outside this local demo.

---

## 5. Verify the application is running

In a second terminal:

```bash
curl --fail http://localhost:8000/healthz   # should return: {"status":"ok"}
curl --fail http://localhost:8000/readyz    # should return: {"status":"ok"}
curl --fail --head http://localhost:5173/  # Vite should respond HTTP 200
```

A failing `/readyz` means the database connection is unavailable. Check
that the PostgreSQL container is still running and that `DATABASE_URL` is set.

---

## 6. Create a demo account

1. Open `http://localhost:5173/register`.
2. Enter any email address and a secure password.
3. Watch the backend terminal for the email verification code (6 digits).
4. Enter the code at the verification screen.
5. Sign in at `http://localhost:5173/login`.

The dashboard loads with built-in sample data. No seed command or database
fixture is required for the UI demo.

---

## 7. Seed backend demo data (optional — for Live API tester)

The Live API tester requires a real backend agent API key. Create one with:

```bash
cd backend
source venv/bin/activate
python manage.py seed_demo
```

This prints an agent name, an API key, and a demo dashboard username.
Previous demo agents are suspended (not deleted). The key is printed only
once; store it temporarily in your terminal session.

---

## 8. Shut down

Press **Ctrl+C** in the `run.sh` terminal. Both servers stop.

To stop the PostgreSQL Docker container:

```bash
docker stop agentgate-demo-pg17
```

(Data is discarded; the container used `--rm`.)

---

## Checks (optional verification)

```bash
# Frontend
cd frontend
npm run lint
npm run build
node --test --test-reporter=spec tests/auth-client.test.mjs tests/session-model.test.mjs

# Backend (SQLite — no PostgreSQL required for unit tests)
cd ../backend
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.test
python manage.py test

# Backend lint
ruff check .
```

For PostgreSQL-specific tests, set `TEST_DATABASE_URL` to a **disposable**
PostgreSQL 17 test database (never a database with data to keep):

```bash
export TEST_DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate_test'
python manage.py test
```

---

## Notes

- Do not use a default socket or port that may select a different PostgreSQL
  version. Explicitly specify `127.0.0.1` and the port in `DATABASE_URL`.
- Run `git diff --check` and `git status` before committing anything. The
  `backend/.env` file is in `.gitignore` and must never be committed.
- If the Vite proxy shows CORS errors, confirm the app is opened at
  `http://localhost:5173` (not `http://127.0.0.1:5173`), and that the backend
  is running at `localhost:8000`. Vite proxies `/api` and `/v1` to `:8000`.
- Do not add a wildcard CORS policy or disable browser security controls as
  a workaround.
