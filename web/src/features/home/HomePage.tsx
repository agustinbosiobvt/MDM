import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useMe } from '../../auth/context'

interface Health {
  status: string
  database: string
}

export function HomePage() {
  const me = useMe()
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    retry: false,
  })

  return (
    <section className="stack">
      <div>
        <h1>Welcome, {me.display_name ?? me.email}</h1>
        <p className="muted">
          BVT Master Data: company, customers, vendors and price lists. You are signed in as{' '}
          <strong>{me.role}</strong>.
        </p>
      </div>
      <div className="card">
        <h2>System status</h2>
        {health.isPending && <p>Checking…</p>}
        {health.isError && <p className="error">API unreachable.</p>}
        {health.data && (
          <dl className="kv">
            <dt>API</dt>
            <dd>{health.data.status}</dd>
            <dt>Database</dt>
            <dd>{health.data.database}</dd>
          </dl>
        )}
      </div>
    </section>
  )
}
