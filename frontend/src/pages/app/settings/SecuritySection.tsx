import { useState, type FormEvent } from 'react'
import {
  activateTotp,
  generateRecoveryCodes,
  getRecoveryCodes,
  getTotpSetup,
  reauthenticate,
  removeTotp,
} from '../../../api/auth'
import AuthField from '../../auth/AuthField'
import SixDigitCodeInput from '../../auth/SixDigitCodeInput'

export default function SecuritySection() {
  const [password, setPassword] = useState('')
  const [unlocked, setUnlocked] = useState(false)
  const [setup, setSetup] = useState<Awaited<ReturnType<typeof getTotpSetup>> | null>(null)
  const [code, setCode] = useState<string[]>(Array(6).fill(''))
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [recoveryCodesChecked, setRecoveryCodesChecked] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function withReauthentication(action: () => Promise<void>) {
    if (!password) {
      setError('Enter your current password to continue.')
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    const currentPassword = password
    setPassword('')
    try {
      await reauthenticate(currentPassword)
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not verify your password.')
    } finally {
      setBusy(false)
    }
  }

  function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void withReauthentication(async () => {
      setSetup(await getTotpSetup())
      setUnlocked(true)
      setRecoveryCodes(null)
    })
  }

  function enableTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void withReauthentication(async () => {
      await activateTotp(code.join(''))
      setSetup(await getTotpSetup())
      setCode(Array(6).fill(''))
      setRecoveryCodes(null)
      setRecoveryCodesChecked(false)
      setMessage('Authenticator app protection is enabled.')
    })
  }

  function disableTotp() {
    if (!window.confirm('Remove authenticator app protection and its recovery codes?')) return
    void withReauthentication(async () => {
      await removeTotp()
      setSetup(await getTotpSetup())
      setRecoveryCodes(null)
      setRecoveryCodesChecked(false)
      setMessage('Authenticator app protection was removed.')
    })
  }

  function showRecoveryCodes() {
    void withReauthentication(async () => {
      const codes = await getRecoveryCodes()
      setRecoveryCodes(codes)
      setRecoveryCodesChecked(true)
      setMessage(
        codes === null
          ? 'No recovery codes are available. Enable TOTP to create them.'
          : codes.length
            ? 'Save these codes now. They are shown only once.'
            : 'These recovery codes have already been shown and cannot be displayed again.',
      )
    })
  }

  function regenerateRecoveryCodes() {
    if (
      !window.confirm(
        'Generate new recovery codes? This will invalidate any recovery codes you saved previously.',
      )
    ) {
      return
    }
    void withReauthentication(async () => {
      const codes = await generateRecoveryCodes()
      setRecoveryCodes(codes)
      setRecoveryCodesChecked(true)
      setMessage('Save these new recovery codes now. They are shown only once.')
    })
  }

  async function copyRecoveryCodes() {
    try {
      await navigator.clipboard.writeText(recoveryCodes?.join('\n') ?? '')
      setMessage('Recovery codes copied. Store them somewhere secure.')
      setError(null)
    } catch {
      setError('Clipboard access was denied. Copy the codes manually and store them securely.')
    }
  }

  return (
    <div className="stack">
      <div className="st-section-head">
        <div>
          <h2>Account security</h2>
          <p className="muted">
            Manage authenticator-app verification and one-time recovery codes.
          </p>
        </div>
      </div>

      {!unlocked ? (
        <form className="st-security-card" onSubmit={unlock}>
          <p className="muted">
            Re-enter your password to view and manage authentication methods.
          </p>
          <AuthField
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Verifying…' : 'Unlock security settings'}
          </button>
        </form>
      ) : (
        <div className="stack">
          <p className="auth-note">
            Each security action requires your current password. Locking hides any displayed
            secret or recovery codes from this page.
          </p>
          <AuthField
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <section className="st-security-card" aria-labelledby="totp-heading">
            <h3 id="totp-heading">Authenticator app</h3>
            {setup?.active ? (
              <>
                <p className="muted">An authenticator app is enabled for this account.</p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={disableTotp}
                >
                  Remove authenticator
                </button>
              </>
            ) : setup?.secret ? (
              <>
                <p className="muted">
                  Add this account to an authenticator app, then enter its current six-digit code.
                </p>
                {setup.totpUrl ? (
                  <p><a href={setup.totpUrl}>Open authenticator setup link</a></p>
                ) : null}
                <p className="st-security-secret">
                  Setup key: <code>{setup.secret}</code>
                </p>
                <form className="st-security-form" onSubmit={enableTotp}>
                  <div>
                    <p className="field-label">Six-digit authenticator code</p>
                    <SixDigitCodeInput
                      value={code}
                      onChange={setCode}
                      disabled={busy}
                      error={Boolean(error)}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={busy || code.some((digit) => !digit)}
                  >
                    {busy ? 'Enabling…' : 'Enable authenticator'}
                  </button>
                </form>
              </>
            ) : null}
          </section>

          {setup?.active ? (
            <section className="st-security-card" aria-labelledby="recovery-heading">
              <h3 id="recovery-heading">Recovery codes</h3>
              <p className="muted">
                Recovery codes can be used once if you lose access to your authenticator.
                Viewing existing codes is a one-time action.
              </p>
              <div className="st-security-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy || recoveryCodesChecked}
                  onClick={showRecoveryCodes}
                >
                  {recoveryCodesChecked ? 'Existing codes already viewed' : 'Show existing codes'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={regenerateRecoveryCodes}
                >
                  Generate new codes
                </button>
              </div>
              {recoveryCodes?.length ? (
                <div className="st-recovery-codes" aria-label="Recovery codes">
                  {recoveryCodes.map((item) => <code key={item}>{item}</code>)}
                </div>
              ) : null}
              {recoveryCodes?.length ? (
                <div className="st-security-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void copyRecoveryCodes()}
                  >
                    Copy recovery codes
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setRecoveryCodes(null)
                      setMessage('Recovery codes hidden from this page.')
                    }}
                  >
                    Hide codes
                  </button>
                </div>
              ) : null}
            </section>
          ) : null}
          <div className="st-security-actions">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy}
              onClick={() => {
                setUnlocked(false)
                setSetup(null)
                setRecoveryCodes(null)
                setRecoveryCodesChecked(false)
                setPassword('')
                setMessage(null)
              }}
            >
              Lock security settings
            </button>
          </div>
        </div>
      )}

      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {message ? <p className="hint" role="status">{message}</p> : null}
    </div>
  )
}
