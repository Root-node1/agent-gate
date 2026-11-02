import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, Menu, X } from 'lucide-react'
import DisplayButton from '../../a11y/DisplayButton'
import Logo from '../../components/Logo'
import GitHubMark from './GitHubMark'
import { LINKS } from './content'

export default function LandingHeader() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const close = () => setOpen(false)

  return (
    <header className="lp-header">
      <div className="lp-header-inner">
        <Link to="/" className="lp-brand" aria-label="AgentGate home">
          <Logo />
        </Link>

        <nav
          id="lp-nav"
          className={`lp-nav${open ? ' is-open' : ''}`}
          aria-label="Main"
        >
          <a href="#how-it-works" onClick={close}>How it works</a>
          <a href="#features" onClick={close}>Features</a>
          <a href={LINKS.readme} onClick={close}>Docs</a>
          <a href={LINKS.github} className="lp-nav-github" onClick={close}>
            <GitHubMark />
            GitHub
          </a>
        </nav>

        <div className="lp-header-actions">
          <DisplayButton className="icon-button lp-display-btn" />
          <Link to={LINKS.demo} className="btn btn-primary lp-header-cta">
            Explore demo
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
          <button
            type="button"
            className="lp-menu-btn"
            aria-expanded={open}
            aria-controls="lp-nav"
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </header>
  )
}
