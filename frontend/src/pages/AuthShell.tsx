import type { ReactNode } from 'react'
import { Link } from 'react-router'
import Logo from '../components/Logo'
import './AuthPages.css'

export default function AuthShell({
  eyebrow = 'Secure dashboard access',
  title,
  description,
  wide = false,
  children,
}: {
  eyebrow?: string
  title: string
  description?: string
  wide?: boolean
  children: ReactNode
}) {
  return (
    <main className="auth-page">
      <section
        className={`auth-card${wide ? ' auth-card-wide' : ''}`}
        aria-labelledby="auth-title"
      >
        <Link to="/" className="auth-brand" aria-label="AgentGate home">
          <Logo />
        </Link>
        <p className="auth-eyebrow">{eyebrow}</p>
        <h1 id="auth-title">{title}</h1>
        {description ? <p className="auth-intro">{description}</p> : null}
        {children}
      </section>
    </main>
  )
}
