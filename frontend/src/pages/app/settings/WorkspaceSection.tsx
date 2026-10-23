import { useState, type FormEvent } from 'react'
import { useToast } from '../../../ui/toast-context'
import { CURRENCIES, EXPIRY_OPTIONS, timezoneOptions, type WorkspaceSettings } from './settingsData'

interface Props {
  saved: WorkspaceSettings
  onSave: (next: WorkspaceSettings) => void
}

export default function WorkspaceSection({ saved, onSave }: Props) {
  const toast = useToast()
  const [draft, setDraft] = useState(saved)
  const [nameError, setNameError] = useState('')
  const [zones] = useState(timezoneOptions)

  const dirty =
    draft.name !== saved.name ||
    draft.currency !== saved.currency ||
    draft.expiryHours !== saved.expiryHours ||
    draft.timezone !== saved.timezone

  function update<K extends keyof WorkspaceSettings>(key: K, value: WorkspaceSettings[K]) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const name = draft.name.trim()
    if (name.length < 2) {
      setNameError('Enter a workspace name of at least 2 characters.')
      return
    }
    setNameError('')
    const next = { ...draft, name }
    setDraft(next)
    onSave(next)
    toast.show('Workspace settings saved.', 'success')
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="form-section">
        <div>
          <h2 className="form-section-title">Workspace</h2>
          <p className="form-section-text">Shown to your team and on exported audit logs.</p>
        </div>
        <div>
          <div className="field">
            <label htmlFor="st-name">Workspace name</label>
            <input
              id="st-name"
              value={draft.name}
              onChange={(e) => update('name', e.target.value)}
              aria-invalid={nameError ? 'true' : undefined}
              aria-describedby={nameError ? 'st-name-error' : undefined}
              autoComplete="organization"
            />
            {nameError && (
              <p id="st-name-error" className="field-error">
                {nameError}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="st-tz">Timezone</label>
            <select id="st-tz" value={draft.timezone} onChange={(e) => update('timezone', e.target.value)}>
              {zones.map((zone) => (
                <option key={zone} value={zone}>
                  {zone.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <p className="hint">Used for daily budgets and report dates.</p>
          </div>
        </div>
      </div>

      <div className="form-section">
        <div>
          <h2 className="form-section-title">Payments and approvals</h2>
          <p className="form-section-text">Defaults for new agents and policies.</p>
        </div>
        <div>
          <div className="field">
            <label htmlFor="st-currency">Default currency</label>
            <select id="st-currency" value={draft.currency} onChange={(e) => update('currency', e.target.value)}>
              {CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="st-expiry">Approval expiry</label>
            <select
              id="st-expiry"
              value={draft.expiryHours}
              onChange={(e) => update('expiryHours', Number(e.target.value))}
              aria-describedby="st-expiry-hint"
            >
              {EXPIRY_OPTIONS.map((o) => (
                <option key={o.hours} value={o.hours}>
                  {o.label}
                </option>
              ))}
            </select>
            <p id="st-expiry-hint" className="hint">
              If nobody approves or denies a request in this time, it expires and nothing is paid.
            </p>
          </div>
        </div>
      </div>

      <div className="form-actions st-form-actions">
        <p className="hint st-demo-note">Demo only: changes last until you reload the page.</p>
        <button type="button" className="btn btn-ghost" onClick={() => setDraft(saved)} disabled={!dirty}>
          Discard changes
        </button>
        <button type="submit" className="btn btn-primary" disabled={!dirty}>
          Save changes
        </button>
      </div>
    </form>
  )
}
