import type { AuditEventType } from '../../../demo/types'
import { EVENT } from '../../../ui/labels'

export default function EventType({ type }: { type: AuditEventType }) {
  const info = EVENT[type]
  return (
    <span className={`au-type tone-${info.tone}`}>
      <span className="au-type-dot" aria-hidden="true" />
      {info.label}
    </span>
  )
}
