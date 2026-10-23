import { Link, useParams } from 'react-router'
import { ShieldQuestion } from 'lucide-react'
import { useDemoState } from '../../demo/store'
import { agentName } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import { useSimulatedLoad } from '../../ui/hooks'
import PageHeader from '../../ui/PageHeader'
import PolicyForm from './policies/PolicyForm'
import './PoliciesPage.css'

export default function PolicyEditPage() {
  const { id } = useParams()
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const policy = state.policies.find((p) => p.id === Number(id))
  const back = { to: '/app/policies', label: 'Policies' }

  if (loading) {
    return (
      <div className="stack-lg" aria-busy="true">
        <div className="skeleton po-title-skeleton" />
        <div className="split po-split">
          <div className="card">
            <SkeletonRows rows={8} />
          </div>
          <div className="card">
            <SkeletonRows rows={5} />
          </div>
        </div>
      </div>
    )
  }

  if (!policy) {
    return (
      <div className="stack-lg">
        <PageHeader title="Policy not found" back={back} />
        <div className="card">
          <EmptyState
            icon={<ShieldQuestion size={24} />}
            title="We couldn't find this policy"
            action={
              <Link to="/app/policies" className="btn btn-primary">
                See all policies
              </Link>
            }
          >
            The link may be wrong, or the policy no longer exists.
          </EmptyState>
        </div>
      </div>
    )
  }

  return (
    <div className="stack-lg">
      <PageHeader
        title={policy.name}
        back={back}
        description={
          <>
            Spending rules for <strong>{agentName(state, policy.agent_id)}</strong>. Changes apply to new requests
            only.
          </>
        }
      />
      <PolicyForm key={policy.id} policy={policy} />
    </div>
  )
}
