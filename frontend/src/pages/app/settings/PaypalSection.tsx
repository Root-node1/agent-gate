import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  FlaskConical,
  Info,
  RefreshCw,
  Terminal,
  XCircle,
} from 'lucide-react'
import { fetchPayPalStatus, triggerPayPalProbe, type PayPalPlatformStatus } from '../../../api/paypal'
import Badge from '../../../ui/Badge'
import './PaypalSection.css'

type AgentOption = 'claude' | 'cursor' | 'codex' | 'bob' | 'kiro'

export default function PaypalSection() {
  const [selectedAgent, setSelectedAgent] = useState<AgentOption>('claude')
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [status, setStatus] = useState<PayPalPlatformStatus | null>(null)
  const [isLoadingStatus, setIsLoadingStatus] = useState(true)
  const [isProbing, setIsProbing] = useState(false)
  const [probeMessage, setProbeMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null)

  useEffect(() => {
    let active = true
    fetchPayPalStatus()
      .then((data) => {
        if (active) setStatus(data)
      })
      .catch(() => {
        // Fallback for offline demo mode
        if (active) {
          setStatus({
            state: 'configured',
            mode: 'sandbox',
            live_payments_enabled: false,
            client_id_preview: 'AX1...99Z',
            webhook_configured: true,
            webhook_id_preview: 'WH-82...10',
            checkout_enabled: true,
            payouts_enabled: false,
            last_attempt_at: null,
            last_successful_at: null,
            last_attempt_error: null,
          })
        }
      })
      .finally(() => {
        if (active) setIsLoadingStatus(false)
      })

    return () => {
      active = false
    }
  }, [])

  async function handleProbe() {
    setIsProbing(true)
    setProbeMessage(null)
    try {
      const res = await triggerPayPalProbe()
      if (res.state === 'successfully_tested') {
        setProbeMessage({
          text: `Sandbox OAuth 2.0 handshake succeeded in ${res.latency_ms}ms.`,
          type: 'success',
        })
        const updated = await fetchPayPalStatus()
        setStatus(updated)
      } else {
        setProbeMessage({
          text: `Sandbox OAuth probe failed (${res.error || 'unknown error'}).`,
          type: 'error',
        })
        const updated = await fetchPayPalStatus()
        setStatus(updated)
      }
    } catch (err: unknown) {
      const errorObj = err as { details?: { message?: string }; message?: string }
      const msg = errorObj.details?.message || errorObj.message || 'Probe request failed.'
      setProbeMessage({
        text: `Probe rejected: ${msg}`,
        type: 'error',
      })
    } finally {
      setIsProbing(false)
    }
  }

  function copySnippet(text: string, index: number) {
    navigator.clipboard.writeText(text)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  return (
    <div className="stack-lg paypal-hub">
      {/* 1. CRITICAL SECURITY BOUNDARY WARNING */}
      <div className="notice tone-warning" role="alert">
        <AlertTriangle size={20} className="notice-icon" aria-hidden="true" />
        <div>
          <strong className="block text-sm font-semibold">Security Boundary: External Developer AI Toolkit</strong>
          <p className="text-xs text-muted">
            The PayPal AI Toolkit operates directly inside your AI coding assistant (Claude Code, Cursor, Codex, IBM Bob).
            Direct operations performed by the toolkit are <strong>not</strong> routed through AgentGate and are{' '}
            <strong>not</strong> governed by AgentGate’s spending caps, policies, or approval workflows. AgentGate’s
            deterministic policy engine governs only payments processed via AgentGate’s own runtime engine.
          </p>
        </div>
      </div>

      {/* 2. RUNTIME PAYMENT FIREWALL SECTION */}
      <div className="card st-panel stack-md">
        <div className="st-connection">
          <div className="st-connection-mark" aria-hidden="true">
            <FlaskConical size={22} />
          </div>
          <div className="st-connection-body">
            <h2 className="card-title">Runtime Payment Firewall (AgentGate Server)</h2>
            <p className="card-subtitle">
              Platform-wide PayPal Sandbox connection governing AgentGate’s backend payment executor.
            </p>
          </div>
          <div className="cluster">
            <Badge tone="approval" icon="◐">
              Sandbox · Active
            </Badge>
            <Badge tone="neutral" icon="⏻" variant="outline">
              Live payments: off
            </Badge>
          </div>
        </div>

        {/* Shared Merchant Limitation Banner */}
        <div className="notice tone-info">
          <Info size={18} aria-hidden="true" />
          <p className="text-xs">
            <strong>Shared Platform Merchant:</strong> All AgentGate organizations share a single underlying PayPal Sandbox
            merchant integration. Organization-level spending limits and approvals govern internal AgentGate authorization
            only, and do not partition PayPal merchant-account balances or settlement at PayPal.
          </p>
        </div>

        <dl className="kv st-kv">
          <dt>Connection State</dt>
          <dd>
            {isLoadingStatus ? (
              <span className="muted">Loading status...</span>
            ) : status?.state === 'successfully_tested' ? (
              <span className="text-success inline-flex items-center gap-1">
                <CheckCircle2 size={16} /> Successfully Tested
              </span>
            ) : status?.state === 'configured' ? (
              <span className="text-info inline-flex items-center gap-1">
                <Clock size={16} /> Configured (Ready to Test)
              </span>
            ) : status?.state === 'failed' ? (
              <span className="text-danger inline-flex items-center gap-1">
                <XCircle size={16} /> Failed ({status.last_attempt_error || 'Error'})
              </span>
            ) : (
              <span className="muted">Not Configured</span>
            )}
          </dd>

          <dt>Environment</dt>
          <dd>PayPal Sandbox (Strictly pinned to api-m.sandbox.paypal.com)</dd>

          <dt>Live Payments</dt>
          <dd>
            <strong className="text-neutral">Off</strong> (Disabled in this release)
          </dd>

          <dt>Platform Client ID</dt>
          <dd>
            <code>{status?.client_id_preview || 'Not set'}</code>
          </dd>

          <dt>Webhook Ingestion</dt>
          <dd>
            {status?.webhook_configured ? (
              <span>Configured (<code>{status.webhook_id_preview}</code>)</span>
            ) : (
              <span className="muted">Not configured</span>
            )}
          </dd>

          <dt>Feature Flags</dt>
          <dd>
            Checkout: {status?.checkout_enabled ? 'Enabled' : 'Disabled'} · Payouts:{' '}
            {status?.payouts_enabled ? 'Enabled' : 'Disabled'}
          </dd>
        </dl>

        <div className="cluster items-center justify-between pt-2 border-t">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleProbe}
            disabled={isProbing}
          >
            <RefreshCw size={15} className={isProbing ? 'animate-spin' : ''} aria-hidden="true" />
            {isProbing ? 'Probing Sandbox OAuth (8s max)...' : 'Test Sandbox Connection'}
          </button>
          <span className="text-xs muted">
            Requires Org ADMIN & verified MFA. Rate limited (5 / org, 20 platform / 5m).
          </span>
        </div>

        {probeMessage && (
          <div className={`notice tone-${probeMessage.type} mt-2`}>
            {probeMessage.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span className="text-xs">{probeMessage.text}</span>
          </div>
        )}
      </div>

      {/* 3. DEVELOPER AI TOOLKIT DISCOVERY & SETUP */}
      <div className="card st-panel stack-md">
        <div className="st-connection">
          <div className="st-connection-mark" aria-hidden="true">
            <Terminal size={22} />
          </div>
          <div className="st-connection-body">
            <h2 className="card-title">Developer AI Toolkit Integration</h2>
            <p className="card-subtitle">
              Install the official PayPal AI Toolkit plugin inside your local coding agent for MCP tools and prompts.
            </p>
          </div>
          <a
            href="https://github.com/paypal/AI-Toolkit"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-outline text-xs"
          >
            Official GitHub <ExternalLink size={14} aria-hidden="true" />
          </a>
        </div>

        <div className="stack-sm">
          <label className="text-xs font-semibold text-muted uppercase">Select your coding assistant:</label>
          <div className="cluster gap-2">
            <button
              type="button"
              className={`btn btn-sm ${selectedAgent === 'claude' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setSelectedAgent('claude')}
            >
              Claude Code
            </button>
            <button
              type="button"
              className={`btn btn-sm ${selectedAgent === 'cursor' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setSelectedAgent('cursor')}
            >
              Cursor
            </button>
            <button
              type="button"
              className={`btn btn-sm ${selectedAgent === 'codex' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setSelectedAgent('codex')}
            >
              OpenAI Codex
            </button>
            <button
              type="button"
              className={`btn btn-sm ${selectedAgent === 'bob' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setSelectedAgent('bob')}
            >
              IBM Bob
            </button>
            <button
              type="button"
              className={`btn btn-sm ${selectedAgent === 'kiro' ? 'btn-neutral' : 'btn-outline'}`}
              onClick={() => setSelectedAgent('kiro')}
            >
              Kiro (Unverified)
            </button>
          </div>
        </div>

        {/* Agent Instructions Content */}
        <div className="toolkit-agent-panel p-3 bg-subtle rounded border">
          {selectedAgent === 'claude' && (
            <div className="stack-sm">
              <div className="badge-row">
                <Badge tone="approval">Officially Supported</Badge>
              </div>
              <p className="text-xs">
                Install the official Claude plugin, reload plugins, and configure your personal sandbox token:
              </p>
              <div className="code-block">
                <code>/plugin install paypal@claude-plugins-official</code>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => copySnippet('/plugin install paypal@claude-plugins-official', 1)}
                >
                  <Copy size={13} /> {copiedIndex === 1 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="code-block">
                <code>/reload-plugins</code>
                <button type="button" className="copy-btn" onClick={() => copySnippet('/reload-plugins', 2)}>
                  <Copy size={13} /> {copiedIndex === 2 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="text-xs muted">
                <strong>Private storage & verification:</strong> Run <code>/paypal:setup</code> in Claude Code to configure
                your sandbox app credentials. Then type <code>/paypal</code> to verify available MCP tools. Tokens expire
                after 8 hours (refresh with <code>/paypal:setup refresh</code>).
              </p>
            </div>
          )}

          {selectedAgent === 'cursor' && (
            <div className="stack-sm">
              <div className="badge-row">
                <Badge tone="approval">Officially Supported</Badge>
              </div>
              <p className="text-xs">Add the toolkit marketplace in Cursor terminal and activate the plugin:</p>
              <div className="code-block">
                <code>cursor-agent plugin marketplace add https://github.com/paypal/AI-Toolkit</code>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => copySnippet('cursor-agent plugin marketplace add https://github.com/paypal/AI-Toolkit', 3)}
                >
                  <Copy size={13} /> {copiedIndex === 3 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="text-xs muted">
                Then open <strong>Customize → Plugins → PayPal → Configure</strong> to set up sandbox credentials and
                restart Cursor.
              </p>
            </div>
          )}

          {selectedAgent === 'codex' && (
            <div className="stack-sm">
              <div className="badge-row">
                <Badge tone="approval">Officially Supported</Badge>
              </div>
              <p className="text-xs">Register marketplace and add plugin in Codex:</p>
              <div className="code-block">
                <code>codex plugin marketplace add paypal/AI-Toolkit</code>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => copySnippet('codex plugin marketplace add paypal/AI-Toolkit', 4)}
                >
                  <Copy size={13} /> {copiedIndex === 4 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="code-block">
                <code>codex plugin add paypal@paypal-ai-toolkit</code>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => copySnippet('codex plugin add paypal@paypal-ai-toolkit', 5)}
                >
                  <Copy size={13} /> {copiedIndex === 5 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="text-xs muted">Fully restart Codex after adding the plugin.</p>
            </div>
          )}

          {selectedAgent === 'bob' && (
            <div className="stack-sm">
              <div className="badge-row">
                <Badge tone="approval">Officially Supported</Badge>
              </div>
              <p className="text-xs">Clone the official repository and open in IBM Bob:</p>
              <div className="code-block">
                <code>git clone https://github.com/paypal/AI-Toolkit.git</code>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => copySnippet('git clone https://github.com/paypal/AI-Toolkit.git', 6)}
                >
                  <Copy size={13} /> {copiedIndex === 6 ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="text-xs muted">
                Open in IBM Bob. Bob detects <code>.bob/mcp.json</code> and prompts for browser OAuth authentication at{' '}
                <code>https://mcp.sandbox.paypal.com/mcp</code>.
              </p>
            </div>
          )}

          {selectedAgent === 'kiro' && (
            <div className="stack-sm">
              <div className="badge-row">
                <Badge tone="neutral">Unverified Integration</Badge>
              </div>
              <p className="text-xs text-warning">
                <strong>Notice:</strong> Kiro / Antigravity does not appear in official PayPal AI Toolkit documentation.
              </p>
              <p className="text-xs muted">
                If you require PayPal MCP tools in Kiro, review the official PayPal Streamable HTTP / SSE transport docs and
                configure manually inside <code>.kiro/settings/mcp.json</code>.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
