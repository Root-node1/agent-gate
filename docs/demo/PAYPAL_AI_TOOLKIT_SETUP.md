# PayPal AI Toolkit Setup

The PayPal AI Toolkit is a developer-workflow plugin for supported AI coding
agents. It is **not an AgentGate runtime dependency** — the AgentGate
application does not load it, and the built-in dashboard demo does not need
it. You can run the full UI demo without any Toolkit setup.

The Toolkit is useful if you are using a supported AI coding agent and want
PayPal skills, commands, and sandbox MCP access during development.

---

## Official References

- [PayPal AI Toolkit repository](https://github.com/paypal/AI-Toolkit) — current README,
  agent-specific installation steps, token setup, and refresh flow.
- [PayPal MCP server documentation](https://developer.paypal.com/ai-tools/mcp-server.md)
  — local and remote MCP server options and transports.
- [PayPal Developer Dashboard — Sandbox apps](https://developer.paypal.com/dashboard/applications/sandbox)
  — create or view your own sandbox application.

Always use the current official documentation. These references were checked
in November 2026; PayPal updates them regularly.

---

## Supported Agents

The PayPal AI Toolkit README (as of November 2026) documents these agents:

| Agent | Installation method | Transport |
|---|---|---|
| **Claude Code** | `/plugin install paypal@claude-plugins-official` | Toolkit plugin system |
| **OpenAI Codex** | `codex plugin marketplace add paypal/AI-Toolkit` | Toolkit plugin system |
| **Cursor** | `cursor-agent plugin marketplace add https://github.com/paypal/AI-Toolkit` | Toolkit plugin system |
| **IBM Bob** | Clone repo and open in Bob | OAuth / Streamable HTTP MCP |

**VS Code GitHub Copilot is not an established supported host** for this Toolkit
based on the official installation instructions. If you use Copilot, check the
current Toolkit README for any new support before proceeding.

**Kiro (Antigravity): Compatibility note below.**

---

## Installation by Agent

### Claude Code

```text
/plugin install paypal@claude-plugins-official
/reload-plugins
```

After reload, type `/paypal` or `@paypal` to list available skills.

### OpenAI Codex

```bash
codex plugin marketplace add paypal/AI-Toolkit
codex plugin add paypal@paypal-ai-toolkit
```

Fully quit and restart Codex after installation.

### Cursor

```bash
cursor-agent plugin marketplace add https://github.com/paypal/AI-Toolkit
```

Then open **Customize** (or type `/plugin`) and install `paypal` at user or
project scope. Fully restart Cursor or reload its window, then confirm the
plugin is listed.

### IBM Bob

```bash
git clone https://github.com/paypal/AI-Toolkit.git
cd AI-Toolkit
```

Open the cloned repository in IBM Bob. Bob discovers `.bob/skills/` and
`.bob/mcp.json`. The supplied configuration uses OAuth with Streamable HTTP
at `https://mcp.sandbox.paypal.com/mcp`; Bob prompts for browser authentication.

---

## Kiro (Antigravity) Compatibility

**Kiro does not appear in the official Toolkit installation instructions.**

The Toolkit uses agent-specific plugin formats (Claude plugin system, Codex
plugin marketplace, Cursor plugin system, IBM Bob's `.bob/` discovery).
None of these formats match Kiro's `.kiro/` agent and skill structure.

Kiro does support MCP servers (configured in `.kiro/settings/mcp.json`).
If PayPal publishes a standard MCP server endpoint compatible with Kiro's
transport, it may be configurable via Kiro's MCP settings — but this has
not been verified, and no Kiro-specific Toolkit documentation exists.

**Do not:**

- Invent a Kiro-specific installation command.
- Load arbitrary third-party extensions without reviewing their source and
  permissions.
- Assume a Claude-specific command will work in Kiro.

**If you need PayPal MCP access in Kiro:** check the current
[PayPal MCP server documentation](https://developer.paypal.com/ai-tools/mcp-server.md)
for supported transports (Streamable HTTP, SSE). If a compatible remote MCP
endpoint is available, you can configure it in `.kiro/settings/mcp.json`.
Test with a sample call before relying on it.

---

## Token Setup and Credentials

1. Create a **sandbox** application at
   [https://developer.paypal.com/dashboard/applications/sandbox](https://developer.paypal.com/dashboard/applications/sandbox).
2. Copy the **Client ID** and **Client Secret** for the sandbox app.
3. Configure the credentials using your agent's supported private storage
   (never a committed config file):
   - **Claude Code:** `/paypal:setup` or `/paypal:setup token`
   - **Cursor:** **Customize → Plugins → PayPal → Configure**
   - **IBM Bob:** complete the browser OAuth flow in **Settings → MCP**

**Never:**

- Share a PayPal client secret in chat, screenshots, or logs.
- Commit credentials to any file in the repository.
- Use Live PayPal credentials with the Toolkit.
- Share your MCP access token (it is different from the application secret).

The Toolkit MCP token and AgentGate's runtime `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`
are separate credentials for separate purposes — do not mix them.

---

## Token Refresh

PayPal MCP access tokens expire (up to 8 hours depending on scope):

- **Claude Code / Cursor:** `/paypal:setup refresh`
- **IBM Bob:** re-authenticate in the browser OAuth flow

---

## What the Toolkit Provides vs. What AgentGate Provides

| Capability | Provided by | Notes |
|---|---|---|
| PayPal MCP tools for agent coding sessions | PayPal AI Toolkit | For the developer's AI agent; not an app dependency |
| Deterministic policy enforcement | AgentGate backend | Runs every payment request through deterministic rules |
| Payment execution (Sandbox) | AgentGate backend (`PayPalExecutor`) | Activated only when `PAYMENT_EXECUTOR=paypal` |
| Webhook ingestion and verification | AgentGate backend | HMAC signature checked before processing |
| Approval and audit trail | AgentGate backend | Append-only, hash-chained audit log in PostgreSQL |
| Dashboard UI | AgentGate frontend | React SPA; built-in demo is browser-memory only |

The Toolkit helps a **developer** work with PayPal APIs. AgentGate wraps
PayPal with deterministic controls so an **AI agent** cannot move money
without passing the policy engine and, where required, human approval.
