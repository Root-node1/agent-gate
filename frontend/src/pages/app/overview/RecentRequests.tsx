import { Link } from 'react-router'
import { agentName } from '../../../demo/selectors'
import type { DemoState, SpendRequest } from '../../../demo/types'
import { formatMoney, formatTimestamp, timeAgo } from '../../../ui/format'
import { DecisionStatus, PaymentStatusBadge } from '../../../ui/StatusBadges'

interface Props {
  state: DemoState
  requests: SpendRequest[]
  now: number
}

export default function RecentRequests({ state, requests, now }: Props) {
  return (
    <div className="table-wrap">
      <table className="table ov-recent">
        <thead>
          <tr>
            <th scope="col">Merchant and agent</th>
            <th scope="col" className="num">
              Amount
            </th>
            <th scope="col" className="ov-recent-wide">
              Decision
            </th>
            <th scope="col" className="ov-recent-wide">
              Payment
            </th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} className="row-link">
              <td>
                <Link to={`/app/transactions/${r.id}`} className="row-anchor">
                  {r.merchant}
                </Link>
                <div className="muted small">
                  {agentName(state, r.agent_id)} ·{' '}
                  <time dateTime={r.created_at} title={formatTimestamp(r.created_at)}>
                    {timeAgo(r.created_at, now)}
                  </time>
                </div>
                <div className="ov-recent-compact">
                  <DecisionStatus decision={r.decision} />
                  <PaymentStatusBadge status={r.payment_status} />
                </div>
              </td>
              <td className="num">{formatMoney(r.amount, r.currency)}</td>
              <td className="ov-recent-wide">
                <DecisionStatus decision={r.decision} />
              </td>
              <td className="ov-recent-wide">
                <PaymentStatusBadge status={r.payment_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
