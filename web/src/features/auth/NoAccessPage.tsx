import { useSearchParams } from 'react-router'

const MESSAGES: Record<string, string> = {
  not_allowed:
    "Your Google account isn't allowed to use this app. Use your @buenavidatrading.com account, or ask an administrator to add you.",
  cancelled: 'Sign-in was cancelled.',
  not_configured:
    "Google sign-in isn't configured on this server yet (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET). See the README.",
  error: "Sign-in didn't complete. Please try again.",
}

export function NoAccessPage() {
  const [params] = useSearchParams()
  const reason = params.get('reason') ?? 'error'
  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1>No access</h1>
        <p role="alert">{MESSAGES[reason] ?? MESSAGES.error}</p>
        <a className="btn btn-block" href="/auth/login">
          Try another account
        </a>
      </div>
    </div>
  )
}
