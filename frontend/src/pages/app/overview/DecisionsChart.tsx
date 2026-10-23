import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { DayCount } from '../../../demo/selectors'
import { DECISION } from '../../../ui/labels'
import { longDay, niceTicks, shortDay } from './helpers'

// Bottom to top: the stack reads "what got through", then "held", then "blocked".
const SERIES = [
  { key: 'allow', color: 'var(--chart-allow)' },
  { key: 'needs_approval', color: 'var(--chart-approval)' },
  { key: 'deny', color: 'var(--chart-deny)' },
] as const

const HEIGHT = 220
const PAD = { top: 12, right: 8, bottom: 28, left: 32 }
const GAP = 2
const RADIUS = 4

/** Column with only its top corners rounded, so it stays square on the baseline. */
function topRoundedRect(x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, h, w / 2)
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`
}

export default function DecisionsChart({ days }: { days: DayCount[] }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)
  const [active, setActive] = useState<number | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const totals = days.map((d) => d.allow + d.deny + d.needs_approval)
  const ticks = niceTicks(Math.max(...totals))
  const yMax = ticks[ticks.length - 1]
  const plotW = Math.max(100, width - PAD.left - PAD.right)
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const band = plotW / days.length
  const barW = Math.min(24, band * 0.6)
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH
  const labelEvery = band < 30 ? 3 : band < 48 ? 2 : 1

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const i = Math.floor((e.clientX - rect.left - PAD.left) / band)
    setActive(i >= 0 && i < days.length ? i : null)
  }

  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const last = days.length - 1
    const current = active ?? last
    const next =
      e.key === 'ArrowLeft' ? Math.max(0, current - 1)
        : e.key === 'ArrowRight' ? Math.min(last, current + 1)
          : e.key === 'Home' ? 0
            : e.key === 'End' ? last
              : null
    if (next === null) return
    e.preventDefault()
    setActive(next)
  }

  const activeDay = active === null ? null : days[active]
  const tipLeft = active === null ? 0 : PAD.left + band * active + band / 2
  const tipSide = active !== null && active > days.length / 2 ? 'left' : 'right'

  return (
    <div className="ov-chart">
      <ul className="ov-legend" aria-label="Legend">
        {SERIES.map((s) => (
          <li key={s.key}>
            <span className="ov-swatch" style={{ background: s.color }} aria-hidden="true" />
            {DECISION[s.key].label}
            <span className="ov-legend-total">{days.reduce((sum, d) => sum + d[s.key], 0)}</span>
          </li>
        ))}
      </ul>

      <div className="ov-chart-plot" ref={wrapRef}>
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label="Decisions per day for the last 14 days. Use the left and right arrow keys to read each day; the full numbers are in the table below."
          tabIndex={0}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive((a) => a ?? days.length - 1)}
          onBlur={() => setActive(null)}
          onKeyDown={onKeyDown}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line className="ov-grid" x1={PAD.left} x2={PAD.left + plotW} y1={y(t)} y2={y(t)} />
              <text className="ov-axis" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {t}
              </text>
            </g>
          ))}

          {days.map((d, i) => {
            const x = PAD.left + band * i + (band - barW) / 2
            const present = SERIES.filter((s) => d[s.key] > 0)
            let base = 0
            return (
              <g key={d.date} className={active === i ? 'ov-col ov-col-active' : 'ov-col'}>
                {active === i && (
                  <rect className="ov-col-hover" x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} />
                )}
                {present.map((s, j) => {
                  const y0 = y(base)
                  base += d[s.key]
                  const y1 = y(base)
                  // A 2px surface gap separates stacked segments.
                  const h = Math.max(1, y0 - y1 - (j > 0 ? GAP : 0))
                  const top = j === present.length - 1
                  return top ? (
                    <path key={s.key} d={topRoundedRect(x, y1, barW, h, RADIUS)} fill={s.color} />
                  ) : (
                    <rect key={s.key} x={x} y={y1} width={barW} height={h} fill={s.color} />
                  )
                })}
                {i % labelEvery === (days.length - 1) % labelEvery && (
                  <text className="ov-axis" x={x + barW / 2} y={HEIGHT - 8} textAnchor="middle">
                    {i === days.length - 1 ? 'Today' : shortDay(d.date)}
                  </text>
                )}
              </g>
            )
          })}
          <line className="ov-baseline" x1={PAD.left} x2={PAD.left + plotW} y1={y(0)} y2={y(0)} />
        </svg>

        {activeDay && (
          <div
            className={`ov-tooltip ov-tooltip-${tipSide}`}
            style={{ left: tipLeft }}
            role="status"
            aria-live="polite"
          >
            <div className="ov-tooltip-title">{longDay(activeDay.date)}</div>
            {[...SERIES].reverse().map((s) => (
              <div key={s.key} className="ov-tooltip-row">
                <span className="ov-line-key" style={{ background: s.color }} aria-hidden="true" />
                <strong>{activeDay[s.key]}</strong>
                <span className="muted">{DECISION[s.key].label.toLowerCase()}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="visually-hidden">
        <table>
          <caption>Decisions per day, last 14 days</caption>
          <thead>
            <tr>
              <th scope="col">Day</th>
              {SERIES.map((s) => (
                <th key={s.key} scope="col">
                  {DECISION[s.key].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <th scope="row">{longDay(d.date)}</th>
                {SERIES.map((s) => (
                  <td key={s.key}>{d[s.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
