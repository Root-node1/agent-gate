import { useState } from 'react'
import { Link } from 'react-router'
import { BookOpen, Check, Copy, ExternalLink, FileJson, HeartPulse, Terminal } from 'lucide-react'
import Badge from '../../../ui/Badge'
import { useToast } from '../../../ui/toast-context'
import { BACKEND_DEV_URL, CURL_EXAMPLE, GITHUB_URL } from './settingsData'

const DOC_LINKS = [
  {
    icon: BookOpen,
    title: 'API reference',
    path: '/api/docs/',
    text: 'Interactive OpenAPI docs for every endpoint.',
  },
  {
    icon: FileJson,
    title: 'OpenAPI schema',
    path: '/api/schema/',
    text: 'Generate a client in any language.',
  },
  {
    icon: HeartPulse,
    title: 'Health check',
    path: '/api/health/',
    text: 'Returns OK when the backend is up.',
  },
]

const PLANNED = [
  { title: 'MCP server', text: 'Let any MCP-capable agent ask AgentGate before it pays.' },
  { title: 'Python and TypeScript SDKs', text: 'One call to submit a request and wait for the decision.' },
  { title: 'Webhooks', text: 'Get notified when a request is decided, approved or paid.' },
]

export default function DevelopersSection() {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  async function copyCurl() {
    try {
      await navigator.clipboard.writeText(CURL_EXAMPLE)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.show("Couldn't copy. Select the text and copy it manually.", 'error')
    }
  }

  return (
    <div className="stack-lg">
      <section className="stack" aria-labelledby="st-docs-heading">
        <div>
          <h2 id="st-docs-heading" className="card-title">
            Documentation
          </h2>
          <p className="card-subtitle">
            Paths are on the AgentGate backend. In local development that's <code>{BACKEND_DEV_URL}</code>.
          </p>
        </div>
        <ul className="grid grid-2 st-links">
          {DOC_LINKS.map(({ icon: Icon, title, path, text }) => (
            <li key={path}>
              <a className="st-link-card" href={`${BACKEND_DEV_URL}${path}`} target="_blank" rel="noreferrer">
                <Icon size={20} aria-hidden="true" className="st-link-icon" />
                <span className="st-link-body">
                  <strong>
                    {title} <ExternalLink size={14} aria-hidden="true" />
                    <span className="visually-hidden"> (opens in a new tab)</span>
                  </strong>
                  <code className="small">{path}</code>
                  <span className="hint">{text}</span>
                </span>
              </a>
            </li>
          ))}
          <li>
            <a className="st-link-card" href={`${GITHUB_URL}#readme`} target="_blank" rel="noreferrer">
              <BookOpen size={20} aria-hidden="true" className="st-link-icon" />
              <span className="st-link-body">
                <strong>
                  README and guides <ExternalLink size={14} aria-hidden="true" />
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </strong>
                <code className="small">github.com/Root-node1/agent-gate</code>
                <span className="hint">Setup, architecture and the rule engine, in README and Doc.md.</span>
              </span>
            </a>
          </li>
        </ul>
      </section>

      <section className="stack" aria-labelledby="st-curl-heading">
        <div className="st-section-head">
          <div>
            <h2 id="st-curl-heading" className="card-title">
              Send your first request
            </h2>
            <p className="card-subtitle">
              Replace <code>agk_YOUR_AGENT_KEY</code> with an agent's key. AgentGate answers with allow, deny or needs
              approval, and the reasons.
            </p>
          </div>
        </div>
        <div className="st-code">
          <div className="st-code-bar">
            <span className="small">
              <Terminal size={14} aria-hidden="true" /> curl
            </span>
            <button type="button" className="btn btn-secondary btn-sm st-copy" onClick={copyCurl}>
              {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <pre tabIndex={0} aria-label="Example curl request">
            <code>{CURL_EXAMPLE}</code>
          </pre>
        </div>
        <p className="hint">
          Prefer a form? Try the <Link to="/app/live">Live API tester</Link>, which calls the real backend from your
          browser.
        </p>
      </section>

      <section className="stack" aria-labelledby="st-planned-heading">
        <h2 id="st-planned-heading" className="card-title">
          Integrations
        </h2>
        <ul className="st-planned">
          <li className="st-planned-item">
            <span>
              <strong>REST API</strong>
              <span className="hint">Agents send spend requests with a Bearer key.</span>
            </span>
            <Badge tone="allow" icon="✓">
              Available
            </Badge>
          </li>
          {PLANNED.map((item) => (
            <li key={item.title} className="st-planned-item">
              <span>
                <strong>{item.title}</strong>
                <span className="hint">{item.text}</span>
              </span>
              <Badge tone="neutral" icon="◷" variant="outline">
                Planned
              </Badge>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
