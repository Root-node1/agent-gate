import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
import Logo from './Logo'

export default function Layout() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    fetch('/api/health/')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <>
      <header className="app-header">
        <Link to="/" className="home-link" aria-label="AgentGate home">
          <Logo />
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end className="nav-link">
            Test a payment
          </NavLink>
          <NavLink to="/requests" className="nav-link">
            Requests
          </NavLink>
          <NavLink to="/approvals" className="nav-link">
            Approvals
          </NavLink>
        </nav>
        <p className="health">Backend: {status}</p>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </>
  )
}
