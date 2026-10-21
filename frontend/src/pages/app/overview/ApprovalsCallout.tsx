import { Link } from 'react-router'
import { ArrowRight, Clock, ShieldCheck } from 'lucide-react'
import { requestById } from '../../../demo/selectors'
import type { Approval, DemoState } from '../../../demo/types'
import { formatMoney, timeAgo } from '../../../ui/format'
import { duration, plural } from './helpers'

interface Props {
  state: DemoState
  /** Pending approvals, oldest first. */
  pending: Approval[]
  now: number
}

export default function ApprovalsCallout({ state, pending, now }: Props) {
  if (pending.length === 0) {
    return (
      <section className="ov-callout ov-callout-clear tone-allow" aria-label="Approvals">
        <ShieldCheck size={22} aria-hidden="true" className="ov-callout-icon" />
        <div className="ov-callout-body">
          <p className="ov-callout-title">All clear: no payments are waiting for approval</p>
          <p className="ov-callout-text">
            Anything over an approval threshold or from an untrusted source will show up here.
          </p>
        </div>
      </section>
    )
  }

  const oldest = pending[0]
  const amounts = pending.map((a) => requestById(state, a.spend_request_id)).filter((r) => r !== undefined)
  const sameCurrency = amounts.every((r) => r.currency === amounts[0]?.currency)
  const held = sameCurrency && amounts.length ? formatMoney(amounts.reduce((s, r) => s + r.amount, 0), amounts[0].currency) : null

  return (
    <section className="ov-callout tone-approval" aria-label="Approvals waiting">
      <Clock size={22} aria-hidden="true" className="ov-callout-icon" />
      <div className="ov-callout-body">
        <p className="ov-callout-title">
          {plural(pending.length, 'payment')} {pending.length === 1 ? 'is' : 'are'} waiting for your approval
          {held && <span className="ov-callout-amount"> · {held} on hold</span>}
        </p>
        <p className="ov-callout-text">
          The oldest has waited {duration(oldest.created_at, now)}
          {new Date(oldest.expires_at).getTime() > now ? ` and expires ${timeAgo(oldest.expires_at, now)}` : ''}.
          Nothing is paid until someone decides.
        </p>
      </div>
      <Link to="/app/approvals" className="btn btn-primary ov-callout-action">
        Review approvals
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </section>
  )
}
