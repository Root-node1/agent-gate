import { Link, useNavigate } from 'react-router'
import { FileQuestion } from 'lucide-react'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import { useSession } from '../session/context'
import './LandingPage.css'
import './NotFoundPage.css'

export default function NotFoundPage() {
  const { authenticationStatus } = useSession()
  const isAuthenticated = authenticationStatus === 'authenticated'
  const navigate = useNavigate()

  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main" className="nfp-main">
        <section className="lp-section lp-hero lp-hero-sm nfp-section" aria-labelledby="nfp-title">
          <div className="lp-container nfp-container">
            <p className="lp-kicker nfp-kicker">404</p>
            <h1 id="nfp-title" className="lp-h1 nfp-heading">
              404 — Page not found
            </h1>
            <p className="lp-lede nfp-lede">
              The page you're looking for doesn't exist, may have moved, or is no longer available.
            </p>
            <div className="nfp-icon" aria-hidden="true">
              <FileQuestion size={48} strokeWidth={1.5} />
            </div>
            <div className="nfp-actions">
              <Link to="/" className="btn btn-primary lp-btn-lg">
                Go to homepage
              </Link>
              {isAuthenticated && (
                <Link to="/app" className="btn btn-outline lp-btn-lg">
                  Open dashboard
                </Link>
              )}
              <button
                type="button"
                className="btn btn-ghost lp-btn-lg"
                onClick={() => navigate(-1)}
              >
                Go back
              </button>
            </div>
          </div>
        </section>
      </main>
      <LandingFooter />
    </div>
  )
}
