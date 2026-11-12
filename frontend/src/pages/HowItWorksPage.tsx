import { ListChecks } from 'lucide-react'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import CodeSample from './landing/CodeSample'
import { STEPS } from './landing/content'
import './LandingPage.css'

export default function HowItWorksPage() {
  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main" tabIndex={-1}>
        <section className="lp-section" id="how-it-works" aria-labelledby="lp-how-title">
          <div className="lp-container lp-how">
            <div>
              <div className="lp-section-head lp-section-head-left">
                <p className="lp-kicker">How it works</p>
                <h1 id="lp-how-title" className="lp-h1">
                  One API call between your agent and the money
                </h1>
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
      </main>
      <LandingFooter />
    </div>
  )
}
