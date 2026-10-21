import { AlertTriangle, CircleCheck, OctagonX } from 'lucide-react'
import { RULE_INFO } from '../demo/rules'
import type { RiskIndicator } from '../demo/selectors'
import type { Reason } from '../demo/types'

/** Why a request got its decision: each rule, whether it blocks or escalates, and its code. */
export default function ReasonList({ reasons }: { reasons: Reason[] }) {
  if (reasons.length === 0) {
    return (
      <ul className="reason-list">
        <li className="reason tone-allow">
          <CircleCheck size={18} className="reason-icon" aria-hidden="true" />
          <div className="reason-body">
            <span>Passed every rule in the policy.</span>
          </div>
        </li>
      </ul>
    )
  }
  return (
    <ul className="reason-list">
      {reasons.map((reason) => {
        const blocks = RULE_INFO[reason.code]?.outcome === 'deny'
        const Icon = blocks ? OctagonX : AlertTriangle
        return (
          <li key={reason.code} className={`reason ${blocks ? 'tone-deny' : 'tone-approval'}`}>
            <Icon size={18} className="reason-icon" aria-hidden="true" />
            <div className="reason-body">
              <span>{reason.message}</span>
              <span className="reason-meta">
                <strong>{blocks ? 'Blocks payment' : 'Needs a person'}</strong>
                <code>{reason.code}</code>
              </span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** Demo-only risk hints for reviewers. */
export function RiskList({ indicators }: { indicators: RiskIndicator[] }) {
  if (indicators.length === 0) {
    return <p className="hint">No risk signals found.</p>
  }
  return (
    <ul className="reason-list">
      {indicators.map((risk) => (
        <li key={risk.label} className={`reason ${risk.level === 'high' ? 'tone-deny' : 'tone-approval'}`}>
          <AlertTriangle size={18} className="reason-icon" aria-hidden="true" />
          <div className="reason-body">
            <span>{risk.label}</span>
            <span className="reason-meta">
              <strong>{risk.level === 'high' ? 'High risk' : 'Worth a look'}</strong>
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}
