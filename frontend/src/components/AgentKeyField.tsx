import { useSession } from '../session/context'

export default function AgentKeyField({ error }: { error?: string }) {
  const { agentKey, setAgentKey } = useSession()

  return (
    <div className="field">
      <label htmlFor="agentKey">Agent key</label>
      <input
        id="agentKey"
        type="password"
        autoComplete="off"
        placeholder="agk_..."
        value={agentKey}
        onChange={(e) => setAgentKey(e.target.value.trim())}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? 'agentKey-error' : 'agentKey-hint'}
        required
      />
      {error ? (
        <span id="agentKey-error" className="field-error">
          {error}
        </span>
      ) : (
        <span id="agentKey-hint" className="hint">
          From <code>manage.py create_agent</code>. Kept in this tab only.
        </span>
      )}
    </div>
  )
}
