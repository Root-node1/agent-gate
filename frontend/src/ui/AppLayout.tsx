import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import {
  Bot,
  CircleCheckBig,
  FlaskConical,
  LayoutDashboard,
  ListOrdered,
  Menu,
  RotateCcw,
  ScrollText,
  Settings,
  SlidersHorizontal,
  Terminal,
  LogOut,
  X,
  type LucideIcon,
} from 'lucide-react'
import DisplayButton from '../a11y/DisplayButton'
import type { AuthUser } from '../api/auth'
import Logo from '../components/Logo'
import { resetDemo, useDemoState } from '../demo/store'
import { pendingApprovals } from '../demo/selectors'
import { useSession } from '../session/context'
import Modal from './Modal'
import { useToast } from './toast-context'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  count?: number
}

export default function AppLayout({ user }: { user: AuthUser }) {
  const state = useDemoState()
  const toast = useToast()
  const { logout } = useSession()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const waiting = pendingApprovals(state).length

  const main: NavItem[] = [
    { to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
    { to: '/app/approvals', label: 'Approvals', icon: CircleCheckBig, count: waiting },
    { to: '/app/transactions', label: 'Transactions', icon: ListOrdered },
    { to: '/app/agents', label: 'Agents', icon: Bot },
    { to: '/app/policies', label: 'Policies', icon: SlidersHorizontal },
    { to: '/app/audit', label: 'Audit log', icon: ScrollText },
  ]
  const demo: NavItem[] = [
    { to: '/app/simulate', label: 'Simulate a request', icon: FlaskConical },
    { to: '/app/live', label: 'Live API tester', icon: Terminal },
  ]

  const renderItem = (item: NavItem) => (
    <li key={item.to}>
      <NavLink to={item.to} end={item.end} className="side-link" onClick={() => setMenuOpen(false)}>
        <item.icon size={18} aria-hidden="true" />
        <span>{item.label}</span>
        {item.count ? (
          <span className="side-count" aria-label={`${item.count} waiting`}>
            {item.count}
          </span>
        ) : null}
      </NavLink>
    </li>
  )

  return (
    <div className={`shell ${menuOpen ? 'shell-menu-open' : ''}`}>
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <aside className="sidebar" aria-label="Sidebar">
        <div className="sidebar-top">
          <Link to="/" className="sidebar-logo" aria-label="AgentGate home">
            <Logo />
          </Link>
          <button
            type="button"
            className="icon-button sidebar-close"
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Dashboard">
          <ul className="side-list">{main.map(renderItem)}</ul>
          <p className="side-heading">Try it</p>
          <ul className="side-list">{demo.map(renderItem)}</ul>
        </nav>
        <div className="sidebar-bottom">
          <ul className="side-list">
            {renderItem({ to: '/app/settings', label: 'Settings', icon: Settings })}
          </ul>
          <div className="user-chip">
            <span className="avatar" aria-hidden="true">
              {user?.username.slice(0, 1).toUpperCase()}
            </span>
            <span>
              <strong>{user?.username}</strong>
              <span className="user-role">Dashboard account</span>
            </span>
          </div>
        </div>
      </aside>
      <div className="sidebar-scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />

      <div className="shell-main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button menu-button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            aria-expanded={menuOpen}
          >
            <Menu size={20} aria-hidden="true" />
          </button>
          <div className="demo-pill">
            <span className="demo-dot" aria-hidden="true" />
            Demo workspace <span className="demo-pill-detail">· sample data, no real money</span>
          </div>
          <DisplayButton />
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              void logout().then(
                () => {
                  toast.show('Signed out.')
                  navigate('/login', { replace: true })
                },
                (error: unknown) =>
                  toast.show(error instanceof Error ? error.message : 'Could not sign out.', 'error'),
              )
            }}
          >
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmReset(true)}>
            <RotateCcw size={16} aria-hidden="true" />
            Reset demo
          </button>
        </header>

        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="Reset the demo?"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                resetDemo()
                setConfirmReset(false)
                toast.show('Demo data reset.')
              }}
            >
              Reset demo
            </button>
          </>
        }
      >
        <p>This puts back the sample agents, policies and requests. Anything you changed is lost.</p>
      </Modal>
    </div>
  )
}
