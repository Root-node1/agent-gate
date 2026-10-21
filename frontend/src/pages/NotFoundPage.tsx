import { Link } from 'react-router'
import { Compass } from 'lucide-react'
import EmptyState from '../ui/EmptyState'

export default function NotFoundPage() {
  return (
    <EmptyState
      icon={<Compass size={24} />}
      title="Page not found"
      action={
        <Link to="/app" className="btn btn-primary">
          Go to the overview
        </Link>
      }
    >
      The link may be old, or the item was removed when the demo was reset.
    </EmptyState>
  )
}
