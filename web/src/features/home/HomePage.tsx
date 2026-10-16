import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

interface Health {
  status: string
  database: string
}

export function HomePage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    retry: false,
  })

  return (
    <section>
      <h1>BVT Master Data</h1>
      <p className="muted">Company, customers, vendors and price lists.</p>
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
