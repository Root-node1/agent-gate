# Local Demo Troubleshooting

**Security rule:** Never include `.env` file contents, passwords, verification
codes, MFA recovery codes, session cookies, PayPal client secrets, or access
tokens in a bug report, chat message, screenshot, or log.

---

## PostgreSQL / database errors

**Check the container version first (Docker option):**

```bash
docker exec agentgate-demo-pg17 pg_isready -U agentgate -d agentgate
docker exec agentgate-demo-pg17 psql -U agentgate -d agentgate -Atc 'SHOW server_version;'
```

Output must start with `17.` — not 18 or 16.

**"EXTENSION syntax error" / "near EXTENSION":**  
You are connected to SQLite, not PostgreSQL. `DATABASE_URL` is not set or is
unset in the current shell. Set it and restart:

```bash
export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
./run.sh
```

**"Could not connect to server" / connection refused:**  
The PostgreSQL container is not running. Start it again (the `--rm` flag means
data is lost on stop — this is expected for the demo):

```bash
docker run --rm -d --name agentgate-demo-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17
```

**"InconsistentMigrationHistory":**  
The existing `db.sqlite3` file has migrations applied that do not match
PostgreSQL. This occurs when the app was run with SQLite before. Use only
PostgreSQL 17 for local development.

**"FATAL: role 'agentgate' does not exist":**  
The database role was not created. Create it on the correct PostgreSQL 17
instance and confirm the port in `DATABASE_URL`. Do not accidentally target
a different PostgreSQL installation.

---

## Missing configuration / environment errors

- Confirm `backend/.env` exists. `run.sh` creates it only if absent.
- For repeat starts, re-export `DATABASE_URL` or add it to `backend/.env`.
  Do not print or share the file contents.
- MFA warning on startup: `MFA_ENCRYPTION_KEY is not configured.` This is an
  expected development warning. TOTP enrollment will fail without the key.
  Generate and add one — see [LOCAL_SETUP.md](LOCAL_SETUP.md) step 4.
- For the UI demo: do not add `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, or
  `PAYMENT_EXECUTOR=paypal`. The executor defaults to `fake`.

---

## Health check failures

```bash
curl --fail http://localhost:8000/healthz   # Django is running
curl --fail http://localhost:8000/readyz    # Django can reach the database
curl --fail --head http://localhost:5173/  # Vite is running
```

- `/healthz` fails → Django is not running. Check the backend terminal for errors.
- `/readyz` fails → Django is running but cannot connect to PostgreSQL.
  Check `DATABASE_URL` and the container status.
- Vite fails → frontend is not started. Check the frontend terminal.

---

## Registration, login, and email verification

- Verification codes appear in the **backend terminal** as plain text (console
  email backend). Check the window running `run.sh`, not your email inbox.
- Use `localhost` (not `127.0.0.1`) consistently for the browser URL to avoid
  cookie domain mismatches.
- If the verification page expires, return to `/register` and register again,
  or request a new code on the verification screen.
- If login shows "Could not verify the dashboard session", the backend may not
  be running. Check `/healthz`.

---

## CSRF / cookie errors

- "CSRF verification failed" (403): reload the app, ensure cookies are enabled,
  and use the same hostname (`localhost`) for all requests.
- Never disable CSRF as a workaround. It protects the session.
- The `csrftoken` cookie must be set by the backend before the first form
  submission. `auth.ts` calls the allauth config endpoint to bootstrap it.

---

## Vite proxy / CORS errors

The Vite dev server proxies `/api`, `/v1`, `/webhooks`, and `/healthz` to
`127.0.0.1:8000`. Open the app at `http://localhost:5173`, not `127.0.0.1:5173`.

If the browser console shows a CORS error:
- Confirm Django is running at `:8000`.
- Confirm the request uses the Vite proxy (URL shows `:5173`, not `:8000`).
- Never add a wildcard `CORS_ALLOWED_ORIGINS='*'` policy.

---

## Port conflicts

If a port is already in use:

```bash
# Find what is using port 8000:
lsof -i :8000
# or
ss -tlnp | grep 8000
```

Stop only the process you recognize as a previous AgentGate instance using
Ctrl+C in its terminal. Do not kill an unknown process.

---

## Frontend build errors

```bash
cd frontend
npm install          # re-install dependencies if package-lock.json changed
npm run build        # check for TypeScript/build errors
npm run lint         # check for ESLint errors
```

If `npm install` shows peer dependency conflicts, do not use `--force` or
`--legacy-peer-deps` without understanding the specific conflict.

---

## PayPal AI Toolkit

- **401 / unauthorized:** tokens expire (up to 8 hours). Refresh:
  - Claude Code / Cursor: `/paypal:setup refresh`
  - IBM Bob: re-authenticate in browser OAuth flow
- **No tools listed:** confirm the plugin is loaded (agent-specific check),
  then restart the agent.
- **Cursor: "token not found":** configure via **Customize → Plugins → PayPal →
  Configure**, not a shell environment variable.
- **IBM Bob authorization error:** complete the browser OAuth flow in
  **Settings → MCP**.
- **Tools not responding / 500 errors:** check the official PayPal status page;
  sandbox outages do occur.
- **Never send credentials to an unofficial or unverified MCP endpoint.**

See [PAYPAL_AI_TOOLKIT_SETUP.md](PAYPAL_AI_TOOLKIT_SETUP.md) for official
references.

---

## Reporting a bug

Include:

- The step you were on (from [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)).
- The browser and OS version.
- The exact non-sensitive error message (not the full `.env` file).
- What commands you ran (without passwords or secrets).
- Output of `curl http://localhost:8000/healthz` and `curl http://localhost:8000/readyz`.
- Output of `git rev-parse HEAD` to confirm the commit.

Do **not** include passwords, session cookies, verification codes, MFA
recovery codes, PayPal credentials, or `.env` contents.
