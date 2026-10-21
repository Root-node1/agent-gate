import { ShieldAlert } from 'lucide-react'
import CopyField from '../../../ui/CopyField'
import { API_ENDPOINT, curlSnippet } from './agentStats'

/** A raw API key, shown once, with how the agent should use it. */
export default function KeyReveal({ agentName, rawKey }: { agentName: string; rawKey: string }) {
  return (
    <div className="stack ag-key-reveal">
      <div className="notice tone-approval" role="alert">
        <ShieldAlert size={20} aria-hidden="true" />
        <div>
          <strong>Copy this key now. It will not be shown again.</strong>
          <br />
          AgentGate only keeps the first 8 characters. If you lose it, create a new key.
        </div>
      </div>
      <div className="field ag-key-field">
        <span className="field-label">API key for {agentName}</span>
        <CopyField value={rawKey} label={`API key for ${agentName}`} />
      </div>
      <div className="stack ag-snippet">
        <p className="small">
          Give the key to your agent. It sends it as a Bearer token with every <code>{API_ENDPOINT}</code> call:
        </p>
        <pre className="ag-code" tabIndex={0} aria-label="Example request">
          <code>{curlSnippet(rawKey)}</code>
        </pre>
      </div>
    </div>
  )
}
