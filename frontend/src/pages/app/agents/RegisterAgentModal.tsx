import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { createAgent, DemoError, useDemoState } from '../../../demo/store'
import { policyForAgent } from '../../../demo/selectors'
import type { Agent } from '../../../demo/types'
import Modal from '../../../ui/Modal'
import { useToast } from '../../../ui/toast-context'
import { agentNameError } from './agentStats'
import KeyReveal from './KeyReveal'

interface Props {
  open: boolean
  onClose: () => void
}

export default function RegisterAgentModal({ open, onClose }: Props) {
  const state = useDemoState()
  const toast = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [touched, setTouched] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ agent: Agent; rawKey: string } | null>(null)

  const nameError = agentNameError(name, state.agents.map((a) => a.name))
  const showNameError = touched && nameError

  function close() {
    setName('')
    setDescription('')
    setTouched(false)
    setFormError(null)
    setCreated(null)
    onClose()
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (nameError) return
    try {
      const result = createAgent(name, description)
      setCreated(result)
      setFormError(null)
      toast.show(`${result.agent.name} registered.`, 'success')
    } catch (err) {
      setFormError(err instanceof DemoError ? err.message : 'Could not register the agent. Try again.')
    }
  }

  if (created) {
    const policy = policyForAgent(state, created.agent.id)
    return (
      <Modal
        open={open}
        onClose={close}
        title="Save your API key"
        className="modal-wide"
        footer={
          <>
            {policy && (
              <Link to={`/app/policies/${policy.id}`} className="btn btn-secondary" onClick={close}>
                Edit spending rules
              </Link>
            )}
            <button type="button" className="btn btn-primary" onClick={close}>
              I've saved it
            </button>
          </>
        }
      >
        <div className="stack">
          <KeyReveal agentName={created.agent.name} rawKey={created.rawKey} />
          <p className="hint">
            {created.agent.name} starts with default limits: $100 per payment, approval above $50, $500 a day and
            $5,000 a month. Adjust them in its policy.
          </p>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Register an agent"
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={close}>
            Cancel
          </button>
          <button type="submit" form="ag-register-form" className="btn btn-primary">
            Register agent
          </button>
        </>
      }
    >
      <form id="ag-register-form" onSubmit={submit} noValidate>
        <p className="hint ag-modal-intro">
          Each agent gets its own API key and spending policy. You can suspend it or replace its key at any time.
        </p>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <div className="field">
          <label htmlFor="ag-name">Name</label>
          <input
            id="ag-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="e.g. travel-booker"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={showNameError ? 'true' : undefined}
            aria-describedby="ag-name-hint ag-name-error"
            autoFocus
          />
          <span id="ag-name-hint" className="hint">
            Lowercase letters, numbers and dashes. Shown in logs and approvals.
          </span>
          {showNameError && (
            <span id="ag-name-error" className="field-error">
              {nameError}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="ag-description">
            Description <span className="muted">(optional)</span>
          </label>
          <textarea
            id="ag-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this agent pay for?"
            maxLength={200}
          />
        </div>
      </form>
    </Modal>
  )
}
