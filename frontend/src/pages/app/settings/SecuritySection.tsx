import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Copy, ShieldCheck } from 'lucide-react'
import {
  activateTotp,
  generateRecoveryCodes,
  getAuthenticators,
  getRecoveryCodes,
  getTotpSetup,
  reauthenticate,
  removeTotp,
} from '../../../api/auth'
import Modal from '../../../ui/Modal'
import { PasswordField, SixDigitCodeInput } from '../../AuthFields'

interface Authenticator {
  type: string
  unused_code_count?: number
}

function isAuthenticator(value: unknown): value is Authenticator {
  return (
    typeof value === 'object' &&
    value !== null &&
    'type' in value &&
    typeof value.type === 'string'
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isSecurityError(cause: unknown): cause is { status: number; responseData: unknown } {
  return (
    typeof cause === 'object' &&
    cause !== null &&
    'status' in cause &&
    typeof (cause as { status?: unknown }).status === 'number' &&
    'responseData' in cause
  )
}

export default function SecuritySection() {
  const pendingAction = useRef<(() => Promise<void>) | null>(null)
  const [loading, setLoading] = useState(true)
  const [totpActive, setTotpActive] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [totpUrl, setTotpUrl] = useState<string | null>(null)
  const [recoveryCount, setRecoveryCount] = useState(0)
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [recoveryAlreadyViewed, setRecoveryAlreadyViewed] = useState(false)
  const [code, setCode] = useState<string[]>(Array(6).fill(''))
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [reauthRequired, setReauthRequired] = useState(false)
  const [reauthPassword, setReauthPassword] = useState('')
  const [confirmAction, setConfirmAction] = useState<'remove' | 'regenerate' | null>(null)

  function needsReauthentication(cause: unknown) {
    if (!isSecurityError(cause) || cause.status !== 401) return false
    if (!isRecord(cause.responseData)) return false
    return (
      Array.isArray(cause.responseData.flows) &&
      cause.responseData.flows.some(
        (flow) => isRecord(flow) && flow.id === 'reauthenticate',
      )
    )
  }

  function handleActionError(cause: unknown, action: () => Promise<void>) {
    if (needsReauthentication(cause)) {
      pendingAction.current = action
      setConfirmAction(null)
      setReauthRequired(true)
      setError(null)
      return
    }
    setError(cause instanceof Error ? cause.message : 'The security action could not be completed.')
  }

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [totp, authenticators] = await Promise.all([
        getTotpSetup(),
        getAuthenticators(),
      ])
      const entries = authenticators.filter(isAuthenticator)
      const recovery = entries.find((item) => item.type === 'recovery_codes')
      setTotpActive(totp.active)
      setSecret(totp.secret ?? null)
      setTotpUrl(totp.totpUrl ?? null)
      setRecoveryCount(recovery?.unused_code_count ?? 0)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load account security settings.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    void Promise.all([getTotpSetup(), getAuthenticators()])
      .then(([totp, authenticators]) => {
        if (!active) return
        const entries = authenticators.filter(isAuthenticator)
        const recovery = entries.find((item) => item.type === 'recovery_codes')
        setTotpActive(totp.active)
        setSecret(totp.secret ?? null)
        setTotpUrl(totp.totpUrl ?? null)
        setRecoveryCount(recovery?.unused_code_count ?? 0)
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : 'Could not load account security settings.',
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  async function enableTotp() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await activateTotp(code.join(''))
      setCode(Array(6).fill(''))
      setNotice('Authenticator app verification is now enabled.')
      await refresh()
      await viewRecoveryCodes()
    } catch (cause) {
      handleActionError(cause, enableTotp)
    } finally {
      setBusy(false)
    }
  }

  async function createRecoveryCodes() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const codes = await generateRecoveryCodes()
      setRecoveryCodes(codes)
      setRecoveryAlreadyViewed(false)
      setRecoveryCount(codes.length)
      setConfirmAction(null)
    } catch (cause) {
      handleActionError(cause, createRecoveryCodes)
    } finally {
      setBusy(false)
    }
  }

  async function viewRecoveryCodes() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const codes = await getRecoveryCodes()
      if (codes?.length) {
        setRecoveryCodes(codes)
        setRecoveryAlreadyViewed(false)
      } else {
        setRecoveryAlreadyViewed(true)
        setNotice('Recovery codes were already viewed. Generate a new set to save them again.')
      }
    } catch (cause) {
      handleActionError(cause, viewRecoveryCodes)
    } finally {
      setBusy(false)
    }
  }

  async function disableTotp() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await removeTotp()
      setConfirmAction(null)
      setNotice('Authenticator app verification has been disabled.')
      await refresh()
    } catch (cause) {
      handleActionError(cause, disableTotp)
    } finally {
      setBusy(false)
    }
  }

  async function copyRecoveryCodes() {
    try {
      await navigator.clipboard.writeText(recoveryCodes?.join('\n') ?? '')
      setNotice('Recovery codes copied. Store them somewhere secure.')
    } catch {
      setError('Clipboard access was denied. Copy the codes manually and store them securely.')
    }
  }

  async function submitReauthentication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await reauthenticate(reauthPassword)
      setReauthRequired(false)
      setReauthPassword('')
      const action = pendingAction.current
      pendingAction.current = null
      if (action) await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Reauthentication failed.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <p role="status">Loading account security settings…</p>
  }

  return (
    <div className="stack">
      <div>
        <h2 className="card-title">Account security</h2>
        <p className="card-subtitle">
          Protect dashboard sign-ins with an authenticator app and one-time recovery codes.
        </p>
      </div>

      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      {notice ? <p className="auth-success" role="status">{notice}</p> : null}

      {reauthRequired ? (
        <form className="card" onSubmit={submitReauthentication}>
          <h3 className="card-title">Confirm it’s you</h3>
          <p className="card-subtitle">
            Re-enter your password before changing account security settings.
          </p>
          <PasswordField
            id="reauth-password"
            label="Current password"
            value={reauthPassword}
            onChange={setReauthPassword}
            autoComplete="current-password"
          />
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Confirming…' : 'Confirm password'}
          </button>
        </form>
      ) : null}

      <section className="card">
        <div className="st-section-head">
          <div>
            <h3 className="card-title">Authenticator app</h3>
            <p className="card-subtitle">Use a time-based one-time password (TOTP) app for sign-in.</p>
          </div>
          <span className={`pill ${totpActive ? 'tone-allow' : 'tone-neutral'}`}>
            {totpActive ? 'Enabled' : 'Not enabled'}
          </span>
        </div>

        {totpActive ? (
          <div className="auth-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmAction('remove')}
              disabled={busy}
            >
              Disable authenticator
            </button>
          </div>
        ) : secret && totpUrl ? (
          <>
            <ol className="auth-security-list">
              <li><span>1.</span><span>Open your authenticator app and add a new account.</span></li>
              <li><span>2.</span><span>Scan the QR code using the app, or enter this setup key manually:</span></li>
            </ol>
            <p className="auth-mono-panel" aria-label="Authenticator setup key">{secret}</p>
            <details>
              <summary>View setup URI</summary>
              <p className="auth-mono-panel">{totpUrl}</p>
            </details>
            <div className="field">
              <label className="field-label">Enter the six-digit code from your app</label>
              <SixDigitCodeInput value={code} onChange={setCode} disabled={busy} error={Boolean(error)} />
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void enableTotp()}
              disabled={busy || code.some((digit) => !digit)}
            >
              {busy ? 'Verifying…' : 'Enable authenticator'}
            </button>
          </>
        ) : (
          <p className="muted">Authenticator setup is not available from the server.</p>
        )}
      </section>

      <section className="card">
        <div className="st-section-head">
          <div>
            <h3 className="card-title">Recovery codes</h3>
            <p className="card-subtitle">
              Use one code if you lose access to your authenticator. Each code works once.
            </p>
          </div>
          <span className="pill tone-neutral">
            {recoveryCount ? `${recoveryCount} unused` : 'Not generated'}
          </span>
        </div>
        {recoveryCodes ? (
          <div className="stack">
            <p className="auth-warning" role="alert">
              Save these codes now. They are shown only once and will not be available again.
            </p>
            <div className="auth-mono-panel" aria-label="Recovery codes">
              {recoveryCodes.map((item) => <div key={item}>{item}</div>)}
            </div>
            <button type="button" className="btn btn-secondary" onClick={() => void copyRecoveryCodes()}>
              <Copy size={16} aria-hidden="true" />
              Copy codes
            </button>
            <button type="button" className="auth-text-button" onClick={() => setRecoveryCodes(null)}>
              I’ve saved these codes
            </button>
          </div>
        ) : (
          <div className="auth-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                if (recoveryCount && !recoveryAlreadyViewed) void viewRecoveryCodes()
                else if (recoveryCount) setConfirmAction('regenerate')
                else void createRecoveryCodes()
              }}
              disabled={busy || !totpActive}
            >
              <ShieldCheck size={16} aria-hidden="true" />
              {recoveryCount && !recoveryAlreadyViewed
                ? 'View recovery codes'
                : recoveryCount
                  ? 'Generate new recovery codes'
                  : 'Generate recovery codes'}
            </button>
            {recoveryCount && !recoveryAlreadyViewed ? (
              <span className="hint">Generating a new set invalidates the current codes.</span>
            ) : !totpActive ? (
              <span className="hint">Enable an authenticator app first.</span>
            ) : null}
          </div>
        )}
      </section>

      <Modal
        open={confirmAction !== null}
        onClose={() => setConfirmAction(null)}
        title={confirmAction === 'remove' ? 'Disable authenticator?' : 'Replace recovery codes?'}
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmAction(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                if (confirmAction === 'remove') void disableTotp()
                if (confirmAction === 'regenerate') void createRecoveryCodes()
              }}
              disabled={busy}
            >
              Confirm
            </button>
          </>
        }
      >
        <p>
          {confirmAction === 'remove'
            ? 'You will no longer need an authenticator code at sign-in. Your recovery codes, if any, remain active.'
            : 'Any existing recovery codes will stop working immediately.'}
        </p>
      </Modal>
    </div>
  )
}
