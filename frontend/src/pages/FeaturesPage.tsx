import {
  Code2,
  KeyRound,
  ScanEye,
  SplitSquareHorizontal,
  UserCheck,
  Wallet,
} from 'lucide-react'
import { RULE_INFO } from '../demo/rules'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import './LandingPage.css'

const FEATURES = [
  {
    icon: Wallet,
    title: 'Spending controls',
    body: 'Daily and monthly budgets, a per-transaction cap, and merchant allow and block lists for each agent.',
    codes: ['OVER_DAILY_BUDGET', 'OVER_TRANSACTION_CAP', 'MERCHANT_BLOCKED'],
  },
  {
    icon: UserCheck,
    title: 'Human approvals',
    body: 'Large or unusual requests wait in a queue. A person approves or denies; payment execution is separate and defaults to a fake executor.',
    codes: ['OVER_APPROVAL_THRESHOLD'],
  },
  {
    icon: ScanEye,
    title: 'Prompt-injection risk',
    body: 'Agents tag where an instruction came from. Anything from a web page, email or invoice fails closed to a human.',
    codes: ['UNTRUSTED_SOURCE', 'UNKNOWN_SOURCE'],
  },
  {
    icon: Code2,
    title: 'Audit trail',
    body: 'Backend API events are written to an append-only log. The built-in dashboard demo timeline is sample data.',
    codes: [],
  },
]

const DETAILS = [
  {
    icon: Code2,
    title: 'Rules in code, not in the model',
    body: 'Decisions are deterministic. A clever prompt cannot talk the gate into a yes.',
  },
  {
    icon: KeyRound,
    title: 'Hashed agent keys',
    body: 'Each agent gets its own key. Only a hash is stored, and a suspended agent is shut out.',
  },
  {
    icon: SplitSquareHorizontal,
    title: 'Decision and payment kept apart',
    body: 'Backend policy decisions and payment execution are separate. The built-in dashboard shows simulated payment outcomes and makes no PayPal calls.',
  },
]

export default function FeaturesPage() {
  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main" tabIndex={-1}>
        <section className="lp-section lp-section-alt" id="features" aria-labelledby="lp-features-title">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Features</p>
              <h1 id="lp-features-title" className="lp-h1">
                Controls that live outside the model
              </h1>
              <p className="lp-section-lede">
                Set the limits once per agent. AgentGate enforces them on every request.
              </p>
            </div>
            <ul className="lp-features">
              {FEATURES.map((f) => (
                <li key={f.title} className="lp-feature">
                  <span className="lp-feature-icon" aria-hidden="true">
                    <f.icon size={22} />
                  </span>
                  <h3 className="lp-h3">{f.title}</h3>
                  <p>{f.body}</p>
                  {f.codes.length > 0 && (
                    <ul className="lp-codes" aria-label="Rule codes">
                      {f.codes.map((code) => (
                        <li
                          key={code}
                          className={`lp-code lp-code-${RULE_INFO[code].outcome}`}
                          title={RULE_INFO[code].label}
                        >
                          {code}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
            <ul className="lp-details">
              {DETAILS.map((d) => (
                <li key={d.title} className="lp-detail">
                  <d.icon size={20} aria-hidden="true" className="lp-detail-icon" />
                  <div>
                    <h3 className="lp-h4">{d.title}</h3>
                    <p>{d.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
      <LandingFooter />
    </div>
  )
}
