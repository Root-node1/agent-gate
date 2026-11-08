import { GitBranch } from 'lucide-react'
import type { AuthOptions } from '../api/auth'

export default function AuthProviders({ options }: { options: AuthOptions }) {
  const providers = [
    { key: 'google', name: 'Google', enabled: options.googleOAuthEnabled, mark: 'G' },
    { key: 'github', name: 'GitHub', enabled: options.githubOAuthEnabled },
  ]
  const enabled = providers.filter((provider) => provider.enabled)

  if (!enabled.length) {
    return <p className="auth-provider-note">Email sign-in is available for this installation.</p>
  }

  return (
    <div className="auth-provider-list">
      {enabled.map((provider) => (
        <form
          key={provider.key}
          method="post"
          action={`/accounts/${provider.key}/login/`}
        >
          <input type="hidden" name="csrfmiddlewaretoken" value={options.csrfToken} />
          <input type="hidden" name="process" value="login" />
          <button type="submit" className="btn btn-secondary btn-block auth-provider">
            <span
              className={`auth-provider-mark auth-${provider.key}-mark`}
              aria-hidden="true"
            >
              {provider.key === 'github' ? <GitBranch size={18} /> : 'G'}
            </span>
            Continue with {provider.name}
          </button>
        </form>
      ))}
    </div>
  )
}
