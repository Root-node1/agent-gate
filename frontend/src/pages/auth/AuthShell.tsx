import type { ReactNode } from 'react'
import { Link } from 'react-router'
import Logo from '../../components/Logo'
import './AuthShell.css'

export default function AuthShell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <main className="auth-shell-page">
      <div className="auth-shell-wrap">
        <Link className="auth-shell-logo" to="/" aria-label="AgentGate home">
          <Logo />
        </Link>
        <section className="auth-shell-card">
          <header className="auth-shell-header">
            <p className="auth-eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            {description ? <p className="muted">{description}</p> : null}
          </header>
          <div className="auth-shell-content">{children}</div>
        </section>
      </div>
    </main>
  )
}
