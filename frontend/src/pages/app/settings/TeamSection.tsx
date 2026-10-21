import { useState, type FormEvent } from 'react'
import { Eye, ShieldCheck, UserCheck, UserPlus } from 'lucide-react'
import type { DemoState, Role } from '../../../demo/types'
import Badge from '../../../ui/Badge'
import { SkeletonRows } from '../../../ui/EmptyState'
import Modal from '../../../ui/Modal'
import { ROLE } from '../../../ui/labels'
import { useToast } from '../../../ui/toast-context'
import { isEmail } from './settingsData'

const ROLE_ICONS = { admin: ShieldCheck, approver: UserCheck, viewer: Eye }
const ROLES: Role[] = ['admin', 'approver', 'viewer']

interface Invite {
  email: string
  role: Role
}

export default function TeamSection({ state, loading }: { state: DemoState; loading: boolean }) {
  const toast = useToast()
  const [invites, setInvites] = useState<Invite[]>([])
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('approver')
  const [error, setError] = useState('')
  const isAdmin = state.currentUser.role === 'admin'

  function openInvite() {
    setEmail('')
    setRole('approver')
    setError('')
    setOpen(true)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const value = email.trim().toLowerCase()
    if (!isEmail(value)) {
      setError('Enter a valid email address, like name@company.com.')
      return
    }
    if (state.team.some((m) => m.email === value) || invites.some((i) => i.email === value)) {
      setError('This person is already on the team or invited.')
      return
    }
    setInvites((list) => [...list, { email: value, role }])
    setOpen(false)
    toast.show(`Invite created for ${value}. Demo only, no email was sent.`, 'success')
  }

  return (
    <div className="stack-lg">
      <div className="st-section-head">
        <div>
          <h2 className="card-title">Team members</h2>
          <p className="card-subtitle">People who can see activity or approve payments in this workspace.</p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={openInvite}>
            <UserPlus size={16} aria-hidden="true" />
            Invite member
          </button>
        )}
      </div>

      <div className="st-table-card">
        {loading ? (
          <SkeletonRows rows={3} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="visually-hidden">Team members and their roles</caption>
              <thead>
                <tr>
                  <th scope="col">Member</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {state.team.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <div className="st-member">
                        <span className="avatar" aria-hidden="true">
                          {member.name.charAt(0)}
                        </span>
                        <span className="st-member-text">
                          <strong>
                            {member.name}
                            {member.id === state.currentUser.id && <span className="muted"> (you)</span>}
                          </strong>
                          <span className="muted small">{member.email}</span>
                        </span>
                      </div>
                    </td>
                    <td>{ROLE[member.role].label}</td>
                    <td>
                      <Badge tone="allow" icon="✓">
                        Active
                      </Badge>
                    </td>
                  </tr>
                ))}
                {invites.map((invite) => (
                  <tr key={invite.email}>
                    <td>
                      <div className="st-member">
                        <span className="avatar st-avatar-invite" aria-hidden="true">
                          {invite.email.charAt(0).toUpperCase()}
                        </span>
                        <span className="st-member-text">
                          <strong>{invite.email}</strong>
                          <span className="muted small">Not joined yet</span>
                        </span>
                      </div>
                    </td>
                    <td>{ROLE[invite.role].label}</td>
                    <td>
                      <Badge tone="neutral" icon="✉" variant="outline">
                        Invited
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <section aria-labelledby="st-roles-heading" className="stack">
        <h2 id="st-roles-heading" className="card-title">
          What each role can do
        </h2>
        <ul className="grid grid-3 st-roles">
          {ROLES.map((r) => {
            const Icon = ROLE_ICONS[r]
            return (
              <li key={r} className="st-role">
                <Icon size={20} aria-hidden="true" className="st-role-icon" />
                <div>
                  <p className="st-role-name">{ROLE[r].label}</p>
                  <p className="hint">{ROLE[r].description}</p>
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Invite a team member"
        footer={
          <>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="submit" form="st-invite-form" className="btn btn-primary">
              Send invite
            </button>
          </>
        }
      >
        <form id="st-invite-form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="st-invite-email">Email address</label>
            <input
              id="st-invite-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={error ? 'true' : undefined}
              aria-describedby={error ? 'st-invite-error' : undefined}
              autoFocus
            />
            {error && (
              <p id="st-invite-error" className="field-error">
                {error}
              </p>
            )}
          </div>
          <fieldset className="st-role-picker">
            <legend className="field-label">Role</legend>
            {ROLES.map((r) => (
              <label key={r} className="st-role-option">
                <input type="radio" name="st-invite-role" value={r} checked={role === r} onChange={() => setRole(r)} />
                <span>
                  <strong>{ROLE[r].label}</strong>
                  <span className="hint">{ROLE[r].description}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="hint">Demo only: no email is sent and the invite is gone after a reload.</p>
        </form>
      </Modal>
    </div>
  )
}
