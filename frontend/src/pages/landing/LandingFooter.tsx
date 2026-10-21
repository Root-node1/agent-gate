import { Link } from 'react-router'
import Logo from '../../components/Logo'
import GitHubMark from './GitHubMark'
import { LINKS } from './content'

export default function LandingFooter() {
  return (
    <footer className="lp-footer">
      <div className="lp-container lp-footer-inner">
        <div className="lp-footer-brand">
          <Logo />
          <p>Built for the PayPal AI Hackathon.</p>
          <p className="lp-footer-note">
            The demo runs on sample data. PayPal payments use the sandbox; no real money moves.
          </p>
        </div>
        <nav className="lp-footer-nav" aria-label="Footer">
          <h2 className="lp-footer-heading">Product</h2>
          <ul>
            <li><Link to={LINKS.demo}>Demo dashboard</Link></li>
            <li><Link to={LINKS.simulate}>Simulator</Link></li>
            <li><Link to={LINKS.audit}>Audit log</Link></li>
          </ul>
        </nav>
        <nav className="lp-footer-nav" aria-label="Resources">
          <h2 className="lp-footer-heading">Resources</h2>
          <ul>
            <li><a href={LINKS.readme}>Documentation</a></li>
            <li><a href={LINKS.design}>Design doc</a></li>
            <li>
              <a href={LINKS.github} className="lp-footer-github">
                <GitHubMark size={16} />
                GitHub
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  )
}
