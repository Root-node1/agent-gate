import { useEffect, useState, type FormEvent } from 'react'
import { AlertCircle, CheckCircle2, LoaderCircle, Server } from 'lucide-react'
import { useToast } from '../../../ui/toast-context'
import { BACKEND_DEV_URL } from './settingsData'

interface BackendConfig {
  url: string
  source: 'env' | 'file' | 'default'
  envLocked: boolean
}

interface ProbeResult {
  ok: boolean
  status?: number
  error?: string
  backend?: string
}

type LoadState = 'loading' | 'desktop' | 'web-only' | 'error'

const SOURCE_LABEL: Record<BackendConfig['source'], string> = {
  env: 'Environment variable (AGENTGATE_BACKEND_URL)',
  file: 'Saved in local desktop configuration',
  default: 'Built-in development default',
}

async function fetchBackendConfig(): Promise<BackendConfig | null> {
  try {
    const res = await fetch('/__agentgate/backend', { credentials: 'same-origin' })
    if (res.status === 404) return null
    if (!res.ok) throw new Error(`Config endpoint returned ${res.status}`)
    return (await res.json()) as BackendConfig
  } catch {
    return null
  }
}

export default function ConnectionSection() {
  const toast = useToast()
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [config, setConfig] = useState<BackendConfig | null>(null)
  const [draft, setDraft] = useState(BACKEND_DEV_URL)
  const [urlError, setUrlError] = useState('')
  const [saving, setSaving] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probe, setProbe] = useState<ProbeResult | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const loaded = await fetchBackendConfig()
      if (cancelled) return
      if (!loaded) {
        setLoadState('web-only')
        return
      }
      setConfig(loaded)
      setDraft(loaded.url)
      setLoadState('desktop')
    })().catch(() => {
      if (!cancelled) setLoadState('error')
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!config || config.envLocked) return
    setSaving(true)
    setUrlError('')
    setProbe(null)
    try {
      const res = await fetch('/__agentgate/backend', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: draft.trim() }),
      })
      const body = (await res.json()) as BackendConfig & { error?: string }
      if (!res.ok) {
        setUrlError(body.error || `Could not save (${res.status})`)
        return
      }
      setConfig({
        url: body.url,
        source: body.source,
        envLocked: body.envLocked,
      })
      setDraft(body.url)
      toast.show('Backend URL saved.', 'success')
    } catch {
      setUrlError('Could not reach the desktop configuration endpoint.')
    } finally {
      setSaving(false)
    }
  }

  async function probeBackend() {
    setProbing(true)
    setProbe(null)
    try {
      const res = await fetch('/__agentgate/backend/probe', {
        method: 'POST',
        credentials: 'same-origin',
      })
      const body = (await res.json()) as ProbeResult
      setProbe(body)
      if (body.ok) toast.show('Backend is reachable.', 'success')
      else toast.show(body.error || 'Backend is unreachable.', 'error')
    } catch {
      setProbe({ ok: false, error: 'Probe request failed' })
      toast.show('Probe request failed.', 'error')
    } finally {
      setProbing(false)
    }
  }

  if (loadState === 'loading') {
    return (
      <div className="stack" role="status">
        <p className="muted">Checking desktop connection settings…</p>
      </div>
    )
  }

  if (loadState === 'web-only') {
    return (
      <div className="stack-lg">
        <section className="stack" aria-labelledby="st-conn-web-heading">
          <div>
            <h2 id="st-conn-web-heading" className="card-title">
              Backend connection
            </h2>
            <p className="card-subtitle">
              You are using the browser web app. The backend URL is whatever origin serves this
              page — there is no separate desktop connection setting here.
            </p>
          </div>
          <div className="st-notice">
            <Server size={16} aria-hidden="true" />
            <p>
              In the AgentGate desktop client, use this tab to point at a separately hosted
              backend (for example <code>https://your-domain.com</code> or{' '}
              <code>{BACKEND_DEV_URL}</code> for local development).
            </p>
          </div>
        </section>
      </div>
    )
  }

  if (loadState === 'error' || !config) {
    return (
      <div className="st-notice st-notice-warn" role="alert">
        <AlertCircle size={16} aria-hidden="true" />
        <p>Could not load desktop connection settings.</p>
      </div>
    )
  }

  const dirty = draft.trim() !== config.url

  return (
    <form onSubmit={save} noValidate>
      <div className="form-section">
        <div>
          <h2 className="form-section-title">Backend URL</h2>
          <p className="form-section-text">
            The desktop client proxies API traffic to a separately hosted AgentGate backend. It
            does not run Django, PostgreSQL, or Redis locally.
          </p>
        </div>
        <div className="stack">
          <div className="field">
            <label htmlFor="st-backend-url">Backend URL</label>
            <input
              id="st-backend-url"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={config.envLocked || saving}
              aria-invalid={urlError ? 'true' : undefined}
              aria-describedby={urlError ? 'st-backend-url-error' : 'st-backend-url-hint'}
              placeholder="https://api.example.com"
              autoComplete="url"
              spellCheck={false}
            />
            {urlError ? (
              <p id="st-backend-url-error" className="field-error">
                {urlError}
              </p>
            ) : (
              <p id="st-backend-url-hint" className="hint">
                HTTPS for hosted backends. HTTP is allowed only for loopback (
                <code>127.0.0.1</code> / <code>localhost</code>). Clear the field and save to
                restore the default.
              </p>
            )}
          </div>

          <dl className="st-conn-meta">
            <div>
              <dt>Active source</dt>
              <dd>{SOURCE_LABEL[config.source]}</dd>
            </div>
            <div>
              <dt>Resolved URL</dt>
              <dd>
                <code>{config.url}</code>
              </dd>
            </div>
          </dl>

          {config.envLocked && (
            <div className="st-notice st-notice-warn">
              <AlertCircle size={16} aria-hidden="true" />
              <p>
                <code>AGENTGATE_BACKEND_URL</code> is set in the process environment and locks
                this setting until the variable is removed.
              </p>
            </div>
          )}

          <div className="st-actions">
            <button type="submit" className="btn btn-primary" disabled={config.envLocked || saving || !dirty}>
              {saving ? 'Saving…' : 'Save backend URL'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={probeBackend}
              disabled={probing}
            >
              {probing ? (
                <>
                  <LoaderCircle size={16} aria-hidden="true" className="spin" />
                  Testing…
                </>
              ) : (
                'Test connection'
              )}
            </button>
          </div>

          {probe && (
            <div
              className={`st-notice ${probe.ok ? '' : 'st-notice-warn'}`}
              role="status"
            >
              {probe.ok ? (
                <CheckCircle2 size={16} aria-hidden="true" />
              ) : (
                <AlertCircle size={16} aria-hidden="true" />
              )}
              <p>
                {probe.ok
                  ? `Reachable (${probe.status ?? 200}) at ${probe.backend ?? config.url}`
                  : probe.error || 'Backend unreachable'}
              </p>
            </div>
          )}
        </div>
      </div>
    </form>
  )
}
