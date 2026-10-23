import type { ReactNode } from 'react'
import { Link } from 'react-router'

interface Props {
  title: string
  description?: ReactNode
  /** Buttons shown on the right. */
  actions?: ReactNode
  back?: { to: string; label: string }
}

export default function PageHeader({ title, description, actions, back }: Props) {
  return (
    <div className="page-header">
      {back && (
        <Link to={back.to} className="page-back">
          ← {back.label}
        </Link>
      )}
      <div className="page-header-row">
        <div>
          <h1 className="page-title">{title}</h1>
          {description && <p className="page-description">{description}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </div>
  )
}
