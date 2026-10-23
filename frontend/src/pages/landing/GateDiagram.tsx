import { useEffect, useState, useSyncExternalStore } from 'react'
import { Bot, Landmark, Pause, Play, ShieldCheck, UserCheck } from 'lucide-react'
import { DecisionStatus } from '../../ui/StatusBadges'
import { RULE_INFO } from '../../demo/rules'
import { SCENARIOS } from './content'

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'
const CYCLE_MS = 5200

function subscribeMotion(onChange: () => void) {
  const media = window.matchMedia(REDUCED_MOTION)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

function useReducedMotion() {
  return useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  )
}

// The hero centerpiece: AI agent -> AgentGate -> PayPal, with a human approver
// branching off the gate. An example request travels the path and lands on one
// of the three outcomes. Cycles on its own until the visitor picks a scenario.
export default function GateDiagram() {
  const reducedMotion = useReducedMotion()
  const [index, setIndex] = useState(0)
  const [run, setRun] = useState(0)
  const [playing, setPlaying] = useState(true)
  const autoplay = playing && !reducedMotion
  const scenario = SCENARIOS[index]

  useEffect(() => {
    if (!autoplay) return
    const timer = window.setInterval(() => {
      setIndex((i) => (i + 1) % SCENARIOS.length)
    }, CYCLE_MS)
    return () => window.clearInterval(timer)
  }, [autoplay])

  function choose(i: number) {
    setPlaying(false)
    setIndex(i)
    setRun((r) => r + 1)
  }

  return (
    <figure className="lp-diagram" aria-labelledby="lp-diagram-caption">
      <figcaption id="lp-diagram-caption" className="visually-hidden">
        Diagram: an AI agent sends a payment request to AgentGate. AgentGate either passes it on to
        PayPal, blocks it, or sends it to a human approver.
      </figcaption>

      <div className="lp-diagram-bar">
        <span className="lp-diagram-title">
          <span className="lp-live-dot" aria-hidden="true" />
          Example request
        </span>
        <div className="lp-tabs" role="group" aria-label="Choose an example request">
          {SCENARIOS.map((s, i) => (
            <button
              key={s.outcome}
              type="button"
              className={`lp-tab lp-tab-${s.outcome}`}
              aria-pressed={i === index}
              onClick={() => choose(i)}
            >
              {s.label}
            </button>
          ))}
          {!reducedMotion && (
            <button
              type="button"
              className="lp-tab lp-tab-icon"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause the animation' : 'Play the animation'}
            >
              {playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
            </button>
          )}
        </div>
      </div>

      <div
        className="lp-stage"
        data-outcome={scenario.outcome}
        key={`${index}-${run}`}
        aria-hidden="true"
      >
        <div className="lp-node lp-node-agent">
          <span className="lp-node-icon">
            <Bot size={24} />
          </span>
          <span className="lp-node-label">AI agent</span>
          <span className="lp-node-sub">asks to pay</span>
        </div>

        <div className="lp-wire lp-wire-in">
          <span className="lp-packet">{scenario.amount}</span>
        </div>

        <div className="lp-node lp-node-gate">
          <span className="lp-node-icon">
            <ShieldCheck size={28} />
            <span className="lp-gate-ring" />
          </span>
          <span className="lp-node-label">AgentGate</span>
          <span className="lp-node-sub">checks rules</span>
        </div>

        <div className="lp-wire lp-wire-out">
          <span className="lp-dot" />
        </div>

        <div className="lp-node lp-node-paypal">
          <span className="lp-node-icon">
            <Landmark size={24} />
          </span>
          <span className="lp-node-label">PayPal</span>
          <span className="lp-node-sub">sandbox</span>
        </div>

        <div className="lp-wire lp-wire-down">
          <span className="lp-dot" />
        </div>

        <div className="lp-node lp-node-human">
          <span className="lp-node-icon">
            <UserCheck size={24} />
          </span>
          <span className="lp-node-label">Human approver</span>
          <span className="lp-node-sub">reviews in the queue</span>
        </div>
      </div>

      <div
        className="lp-verdict"
        key={`v-${index}-${run}`}
        aria-live={autoplay ? 'off' : 'polite'}
      >
        <dl className="lp-request">
          <div>
            <dt>Amount</dt>
            <dd>{scenario.amount} USD</dd>
          </div>
          <div>
            <dt>Merchant</dt>
            <dd className="lp-mono">{scenario.merchant}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{scenario.sourceLabel}</dd>
          </div>
        </dl>
        <div className="lp-result">
          <div className="lp-result-head">
            <DecisionStatus decision={scenario.outcome} />
            <span className="lp-result-text">{scenario.result}</span>
          </div>
          {scenario.codes.length > 0 ? (
            <ul className="lp-codes" aria-label="Rules that fired">
              {scenario.codes.map((code) => (
                <li key={code} className={`lp-code lp-code-${RULE_INFO[code].outcome}`}>
                  {code}
                </li>
              ))}
            </ul>
          ) : (
            <p className="lp-codes-none">No rules fired</p>
          )}
        </div>
      </div>
    </figure>
  )
}
