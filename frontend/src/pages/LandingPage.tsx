import { Link } from 'react-router'
import {
  ArrowRight,
  BookOpen,
  Check,
  CircleAlert,
  Code2,
  FileClock,
  KeyRound,
  ListChecks,
  ScanEye,
  SplitSquareHorizontal,
  UserCheck,
  Wallet,
  X,
} from 'lucide-react'
import { DecisionStatus } from '../ui/StatusBadges'
import { RULE_INFO } from '../demo/rules'
import CodeSample from './landing/CodeSample'
import GateDiagram from './landing/GateDiagram'
import LandingFooter from './landing/LandingFooter'
import LandingHeader from './landing/LandingHeader'
import { LINKS, SCENARIOS, STEPS } from './landing/content'
import './LandingPage.css'

const OUTCOME_ICON = { allow: Check, deny: X, needs_approval: CircleAlert }

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
    body: 'Large or unusual payments wait in a queue. A person approves or denies, and only then does money move.',
    codes: ['OVER_APPROVAL_THRESHOLD'],
  },
  {
    icon: ScanEye,
    title: 'Prompt-injection risk',
    body: 'Agents tag where an instruction came from. Anything from a web page, email or invoice fails closed to a human.',
    codes: ['UNTRUSTED_SOURCE', 'UNKNOWN_SOURCE'],
  },
  {
    icon: FileClock,
    title: 'Audit trail',
    body: 'Every request, decision, approval and payment is written to an append-only log you can review later.',
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
    body: '"Allowed" and "Paid" are separate statuses, so you always know what PayPal confirmed.',
  },
]

export default function LandingPage() {
  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />

      <main id="main" tabIndex={-1}>
        <section className="lp-hero" aria-labelledby="lp-hero-title">
          <div className="lp-container lp-hero-inner">
            <p className="lp-eyebrow">
              <span className="lp-eyebrow-dot" aria-hidden="true" />
              Built for the PayPal AI Hackathon
            </p>
            <h1 id="lp-hero-title" className="lp-hero-title">
              A firewall for AI agent payments
            </h1>
            <p className="lp-hero-lede">
              Your agent can spend money. AgentGate checks every payment against your rules before
              it reaches PayPal, then allows it, blocks it, or asks a human.
            </p>
            <div className="lp-hero-ctas">
              <Link to={LINKS.demo} className="btn btn-primary lp-btn-lg">
                Explore Demo
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <a href={LINKS.readme} className="btn btn-secondary lp-btn-lg">
                <BookOpen size={18} aria-hidden="true" />
                View Documentation
              </a>
            </div>
            <p className="lp-hero-note">No sign-up. Runs on sample data.</p>
          </div>
          <div className="lp-container lp-hero-visual">
            <GateDiagram />
          </div>
        </section>

        <section className="lp-section" id="outcomes" aria-labelledby="lp-outcomes-title">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Decisions</p>
              <h2 id="lp-outcomes-title" className="lp-h2">
                Every request gets one of three answers
              </h2>
              <p className="lp-section-lede">
                Each answer comes with the rule codes that produced it, so you can see exactly why.
              </p>
            </div>
            <ul className="lp-outcomes">
              {SCENARIOS.map((s) => {
                const Icon = OUTCOME_ICON[s.outcome]
                return (
                  <li key={s.outcome} className={`lp-outcome lp-outcome-${s.outcome}`}>
                    <div className="lp-outcome-top">
                      <span className="lp-outcome-icon" aria-hidden="true">
                        <Icon size={20} strokeWidth={2.5} />
                      </span>
                      <h3 className="lp-h3">{s.label}</h3>
                    </div>
                    <p className="lp-outcome-example">
                      <span className="lp-outcome-amount">{s.amount}</span> to{' '}
                      <span className="lp-mono">{s.merchant}</span>
                    </p>
                    <p className="lp-outcome-source">Source: {s.sourceLabel}</p>
                    <p className="lp-outcome-explain">{s.explain}</p>
                    <div className="lp-outcome-foot">
                      <DecisionStatus decision={s.outcome} />
                      {s.codes.length > 0 ? (
                        <ul className="lp-codes" aria-label="Rules that fired">
                          {s.codes.map((code) => (
                            <li
                              key={code}
                              className={`lp-code lp-code-${RULE_INFO[code].outcome}`}
                              title={RULE_INFO[code].label}
                            >
                              {code}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="lp-codes-none">No rules fired</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        </section>

        <section className="lp-section lp-section-alt" id="features" aria-labelledby="lp-features-title">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Features</p>
              <h2 id="lp-features-title" className="lp-h2">
                Controls that live outside the model
              </h2>
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

        <section className="lp-section" id="how-it-works" aria-labelledby="lp-how-title">
          <div className="lp-container lp-how">
            <div>
              <div className="lp-section-head lp-section-head-left">
                <p className="lp-kicker">How it works</p>
                <h2 id="lp-how-title" className="lp-h2">
                  One API call between your agent and the money
                </h2>
              </div>
              <ol className="lp-steps">
                {STEPS.map((step, i) => (
                  <li key={step.title} className="lp-step">
                    <span className="lp-step-num" aria-hidden="true">
                      {i + 1}
                    </span>
                    <div>
                      <h3 className="lp-h4">{step.title}</h3>
                      <p>{step.body}</p>
                    </div>
                  </li>
                ))}
              </ol>
              <aside className="lp-limits" aria-label="Limits">
                <ListChecks size={20} aria-hidden="true" />
                <p>
                  <strong>What it does not do.</strong> AgentGate cannot stop an agent from being
                  tricked. It limits what a tricked agent can spend and puts a person in front of
                  anything risky. PayPal execution is sandbox only and still in development.
                </p>
              </aside>
            </div>
            <CodeSample />
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="lp-cta-title">
          <div className="lp-container lp-cta-inner">
            <div>
              <h2 id="lp-cta-title" className="lp-h2">
                Watch a request get checked
              </h2>
              <p>
                Run the three scenarios in the simulator: allowed, denied and needs approval. Then
                approve one from the queue.
              </p>
            </div>
            <div className="lp-cta-actions">
              <Link to={LINKS.simulate} className="btn lp-btn-lg lp-btn-invert">
                See it decide
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <a href={LINKS.github} className="btn lp-btn-lg lp-btn-outline-invert">
                View on GitHub
              </a>
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />
    </div>
  )
}
