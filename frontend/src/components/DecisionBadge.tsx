import type { Decision } from '../api/spendRequests'
import { DECISION_LABELS } from './labels'

export default function DecisionBadge({
  decision,
  label,
}: {
  decision: Decision
  label?: string
}) {
  const { icon, label: decisionLabel } = DECISION_LABELS[decision]
  return (
    <span className={`badge badge-${decision}`}>
      <span aria-hidden="true">{icon}</span>
      {label ?? decisionLabel}
    </span>
  )
}
