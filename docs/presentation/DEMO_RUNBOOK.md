# AgentGate — Demo Runbook

**Branch:** `integration/agentgate-dashboard`
**Presentation date:** 10 November 2026
**Demo environment:** Local backend or deployed VPS (pending access)

---

## 1. Prerequisites

| Item | Requirement | Status |
|---|---|---|
| Backend running | Django on port 8000 (local) or VPS | ⏳ Pending VPS access |
| Frontend built | `npm run build` completed | ✅ Verified |
| Test account | Pre-registered user with organization | ⏳ Needs preparation |
| MFA key | `MFA_ENCRYPTION_KEY` configured | ⏳ Required for MFA demo |
| VPS access | SSH to `vps.zindika.app` | ⏳ Port 22 timed out |

---

## 2. Test Account Preparation

### Option A: Local Backend (Development)

```bash
cd /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard/backend

# Create a test user via Django shell
python manage.py shell << 'EOF'
from django.contrib.auth import get_user_model
from apps.accounts.models import Organization, OrgMembership, AccountProfile

User = get_user_model()

# Create organization
org, _ = Organization.objects.get_or_create(name="Demo Corp")

# Create user
user = User.objects.create_user(
    username="demo-viewer",
    email="demo@agentgate.test",
    password="DemoPassword123!"
)

# Create membership
OrgMembership.objects.create(
    user=user,
    organization=org,
    role=OrgMembership.Role.ADMIN
)

# Create profile
AccountProfile.objects.create(
    user=user,
    full_name="Demo Viewer"
)

print(f"User: {user.username} ({user.email})")
print(f"Organization: {org.name}")
print(f"Role: admin")
EOF
```

### Option B: Deployed VPS

Register through the frontend at `https://app.example.com/register` with:
- Full name: Demo Viewer
- Email: demo@agentgate.test
- Organization: Demo Corp
- Password: DemoPassword123!

---

## 3. Demo Script (10 Steps)

### Step 1: Open AgentGate

**Action:** Navigate to `https://app.example.com` (or `http://localhost:8000` for local)
**Expected:** Landing page loads
**Fallback:** If VPS unreachable, use local backend

### Step 2: Register or Sign In

**Action:** Use the prepared test account (demo-viewer / DemoPassword123!)
**Expected:** Sign-in successful; session established; redirect to `/app`
**Fallback:** If registration needed, use Register page with test data

### Step 3: Restore Session

**Action:** Refresh the browser page
**Expected:** User remains authenticated; no re-login required
**Notes:** Demonstrates session cookie persistence

### Step 4: Navigate Dashboard

**Action:** Browse the dashboard navigation (spend requests, approvals, agents, policies)
**Expected:** Pages load without errors; role-appropriate content shown
**Fallback:** If some pages are placeholders, demonstrate available pages only

### Step 5: View Profile

**Action:** Navigate to Settings → Profile (or account menu → profile)
**Expected:** Profile displays full_name and membership info
**Fallback:** Show CurrentUserSerializer data if UI not available

### Step 6: Show Organization Association

**Action:** Display user's organization membership in profile or team settings
**Expected:** "Demo Corp" with role "Admin" visible
**Notes:** Demonstrates Organization + OrgMembership domain model

### Step 7: Show Security Settings

**Action:** Navigate to Settings → Security
**Expected:** TOTP status (enabled/not enabled), recovery code status
**Fallback:** If MFA_ENCRYPTION_KEY not configured, show "not available" state honestly

### Step 8: Desktop Application (if Tauri build verified)

**Action:** Launch AgentGate desktop app; sign in
**Expected:** App launches; connects to backend; session works
**Fallback:** Skip if unsigned build not verified — document as planned

### Step 9: Explain Deployed Backend and Backups

**Action:** Show `/healthz` endpoint; explain backup strategy
**Expected:** Health check returns 200; backup docs available
**Fallback:** Show local health endpoint; explain VPS deployment plan

### Step 10: Log Out

**Action:** Click logout
**Expected:** Session destroyed; redirect to login page
**Notes:** Demonstrates session termination

---

## 4. What to Avoid Demonstrating

| Feature | Reason | Alternative |
|---|---|---|
| MFA enrollment/activation | `MFA_ENCRYPTION_KEY` not configured; app fails closed | Show Security section UI, explain MFA is configured but key needed |
| OAuth (GitHub/Google) | No OAuth credentials configured | Show "Email sign-in available" state |
| Password reset | No email backend configured | Explain email verification is mandatory but email sending needs SMTP |
| PayPal sandbox | Excluded from this deployment | Explicitly state PayPal is a separate development concern |
| Production payment execution | `PAYMENTS_EXECUTION_ENABLED=false` | Explain execution is gated behind explicit flag |

---

## 5. If VPS Connectivity Fails

1. **Primary:** Use local backend (`python manage.py runserver 8000` + `npm run dev`)
2. **Secondary:** Show screenshots/recorded demo of deployed features
3. **Tertiary:** Show code and documentation; explain deployment plan

---

## 6. Demo Environment Checklist (Day Of)

- [ ] Backend running and accessible
- [ ] Test account created (demo-viewer)
- [ ] `MFA_ENCRYPTION_KEY` configured (if MFA demo needed)
- [ ] Frontend built (`dist/` exists)
- [ ] Health endpoint responding (`/healthz`)
- [ ] Tauri app built (if desktop demo)
- [ ] Backup documentation ready to show
- [ ] Slide content loaded in Gamma