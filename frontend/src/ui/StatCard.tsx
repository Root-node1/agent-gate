import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { Tone } from './labels'

interface Props {
  label: string
  value: ReactNode
  /** Small line under the value, e.g. "12% of requests". */
  detail?: ReactNode
  tone?: Tone
  icon?: ReactNode
  /** Makes the whole card a link. */
  to?: string
}

export default function StatCard({ label, value, detail, tone = 'neutral', icon, to }: Props) {
  const body = (
    <>
      <div className="stat-head">
        <span className="stat-label">{label}</span>
        {icon && (
          <span className={`stat-icon tone-${tone}`} aria-hidden="true">
            {icon}
          </span>
        )}
      </div>
      <div className="stat-value">{value}</div>
      {detail && <div className="stat-detail">{detail}</div>}
    </>
  )
  return to ? (
    <Link to={to} className="card stat-card stat-card-link">
      {body}
    </Link>
  ) : (
    <div className="card stat-card">{body}</div>
  )
}
