import { Link, useParams } from 'react-router'
import { ShieldQuestion } from 'lucide-react'
import { getDemoState } from '../../demo/store'
import { getPolicy } from '../../api/policies'
import { useApiResource } from '../../api/useApiResource'
import { agentName } from '../../demo/selectors'
import EmptyState, { SkeletonRows } from '../../ui/EmptyState'
import PageHeader from '../../ui/PageHeader'
import PolicyForm from './policies/PolicyForm'
import './PoliciesPage.css'

export default function PolicyEditPage() {
  const { id } = useParams()
  const state = getDemoState()
  const resource = useApiResource((signal) => id ? getPolicy(id, signal) : Promise.reject(new Error('No policy ID')))
  const loading = resource.status === 'loading'

  // Error state handling
  if (resource.status === 'error') {
    return (
      <div className="stack-lg">
        <PageHeader title="Edit policy" description="Failed to load policy" back={{ to: '/app/policies', label: 'Policies' }} />
        <EmptyState
          icon={<ShieldQuestion size={24} />}
          title="Unable to load policy"
          action={<Link to="/app/policies" className="btn btn-secondary">Back to policies</Link>}
        >
          <span role="alert">{resource.error.message}</span>
        </EmptyState>
      </div>
    )
  }

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
