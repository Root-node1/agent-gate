import type { ReactNode } from 'react'
import type { StatusLabel, Tone } from './labels'

interface Props {
  tone: Tone
  icon?: string
  /** "solid" for policy decisions, "outline" for payment status, so the two never look alike. */
  variant?: 'solid' | 'outline'
  children: ReactNode
  title?: string
}

export default function Badge({ tone, icon, variant = 'solid', children, title }: Props) {
  return (
    <span className={`pill tone-${tone} pill-${variant}`} title={title}>
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  )
}

export function StatusBadge({
  status,
  variant,
  title,
}: {
  status: StatusLabel
  variant?: 'solid' | 'outline'
  title?: string
}) {
  return (
    <Badge tone={status.tone} icon={status.icon} variant={variant} title={title}>
      {status.label}
    </Badge>
  )
}
