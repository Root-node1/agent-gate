import type { AuditEvent, DemoState } from '../demo/types'
import { describeEvent } from './events'
import { formatTimestamp } from './format'
import { EVENT } from './labels'

interface Props {
  state: DemoState
  /** Oldest first. */
  events: AuditEvent[]
}

/** Vertical event timeline, e.g. everything that happened to one request. */
export default function Timeline({ state, events }: Props) {
  if (events.length === 0) return <p className="hint">No events recorded yet.</p>
  return (
    <ol className="timeline">
      {events.map((event) => {
        const info = EVENT[event.event_type]
        return (
          <li key={event.id} className={`timeline-item tone-${info.tone}`}>
            <span className="timeline-dot" aria-hidden="true" />
            <div>
              <p className="timeline-title">{info.label}</p>
              <p className="timeline-meta">
                <time dateTime={event.created_at}>{formatTimestamp(event.created_at)}</time> · by {event.actor}
              </p>
              <p className="timeline-detail">{describeEvent(state, event)}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
