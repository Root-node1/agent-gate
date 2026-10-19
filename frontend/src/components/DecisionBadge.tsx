import type { Decision } from '../api/spendRequests'
import { DECISION_LABELS } from './labels'

export default function DecisionBadge({ decision }: { decision: Decision }) {
  const { icon, label } = DECISION_LABELS[decision]
  return (
    <span className={`badge badge-${decision}`}>
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  )
}
