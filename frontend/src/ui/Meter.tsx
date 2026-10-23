import { formatMoney, percent } from './format'

interface Props {
  label: string
  used: number
  limit: number
  currency: string
}

/** Budget bar. Turns amber at 75% and red at 90%, and says so in words. */
export default function Meter({ label, used, limit, currency }: Props) {
  const pct = percent(used, limit)
  const tone = pct >= 90 ? 'deny' : pct >= 75 ? 'approval' : 'allow'
  const left = Math.max(0, limit - used)
  return (
    <div className={`meter tone-${tone}`}>
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="num">
          {formatMoney(used, currency)} <span className="muted">of {formatMoney(limit, currency)}</span>
        </span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={used}
        aria-valuetext={`${pct}% used, ${formatMoney(left, currency)} left`}
      >
        <div className="meter-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="meter-foot">
        {pct}% used · {formatMoney(left, currency)} left
        {pct >= 90 ? ' · almost at the limit' : pct >= 75 ? ' · getting close' : ''}
      </div>
    </div>
  )
}
