export function LoginPage() {
  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1>BVT Master Data</h1>
        <p className="muted">Sign in with your Buena Vida Trading Google account.</p>
        {/* A full-page navigation: the API runs the whole OAuth flow server-side. */}
        <a className="btn btn-primary btn-block" href="/auth/login">
          Sign in with Google
        </a>
      </div>
    </div>
  )
}
