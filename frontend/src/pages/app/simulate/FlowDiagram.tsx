import { ArrowRight, Bot, CreditCard, OctagonX, ScrollText, ShieldCheck, UserCheck } from 'lucide-react'
import type { Decision } from '../../../demo/types'
import { RULE_COUNT } from './scenarios'

interface Props {
  /** The decision to highlight, or null before anything ran. */
  outcome: Decision | null
  checking: boolean
}

const OUTCOMES = [
  { decision: 'allow', icon: CreditCard, title: 'PayPal', text: 'Allowed: paid automatically', tone: 'allow' },
  { decision: 'needs_approval', icon: UserCheck, title: 'A person', text: 'Needs approval: a human decides', tone: 'approval' },
  { decision: 'deny', icon: OctagonX, title: 'Blocked', text: 'Denied: nothing is paid', tone: 'deny' },
] as const

/** Agent → AgentGate → PayPal / person / blocked → audit log, with the current path highlighted. */
export default function FlowDiagram({ outcome, checking }: Props) {
  const ran = outcome !== null && outcome !== 'pending'
  return (
    <ol className={`sim-flow ${checking ? 'sim-flow-checking' : ''}`} aria-label="How a request flows">
      <li className={`sim-flow-step ${ran || checking ? 'sim-flow-on' : ''}`}>
        <span className="sim-flow-icon tone-info" aria-hidden="true">
          <Bot size={20} />
        </span>
        <span>
          <strong>AI agent</strong>
          <span className="sim-flow-text">Asks to pay a merchant</span>
        </span>
      </li>
      <li className="sim-flow-arrow" aria-hidden="true">
        <ArrowRight size={18} />
      </li>
      <li className={`sim-flow-step sim-flow-gate ${ran || checking ? 'sim-flow-on' : ''}`}>
        <span className="sim-flow-icon tone-info" aria-hidden="true">
          <ShieldCheck size={20} />
        </span>
        <span>
          <strong>AgentGate</strong>
          <span className="sim-flow-text">Checks {RULE_COUNT} policy rules</span>
        </span>
      </li>
      <li className="sim-flow-arrow" aria-hidden="true">
        <ArrowRight size={18} />
      </li>
      <li className="sim-flow-outcomes">
        <ul>
          {OUTCOMES.map((o) => {
            const active = ran && outcome === o.decision
            return (
              <li
                key={o.decision}
                className={`sim-flow-step sim-flow-outcome ${active ? 'sim-flow-on' : ''} ${ran && !active ? 'sim-flow-dim' : ''}`}
              >
                <span className={`sim-flow-icon tone-${o.tone}`} aria-hidden="true">
                  <o.icon size={18} />
                </span>
                <span>
                  <strong>{o.title}</strong>
                  <span className="sim-flow-text">{o.text}</span>
                  {active && <span className="visually-hidden"> (this request)</span>}
                </span>
              </li>
            )
          })}
        </ul>
      </li>
      <li className="sim-flow-arrow" aria-hidden="true">
        <ArrowRight size={18} />
      </li>
      <li className={`sim-flow-step ${ran ? 'sim-flow-on' : ''}`}>
        <span className="sim-flow-icon tone-neutral" aria-hidden="true">
          <ScrollText size={20} />
        </span>
        <span>
          <strong>Audit log</strong>
          <span className="sim-flow-text">Every step is recorded</span>
        </span>
      </li>
    </ol>
  )
}
