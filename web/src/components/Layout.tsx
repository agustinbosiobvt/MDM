import { useMutation, useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router'
import { api } from '../api/client'
import { hasRole, useMe, type Role } from '../auth/context'

const NAV: { to: string; label: string; end?: boolean; minRole?: Role }[] = [
  { to: '/', label: 'Home', end: true },
  { to: '/company', label: 'Company' },
  { to: '/customers', label: 'Customers' },
  { to: '/vendors', label: 'Vendors' },
  { to: '/users', label: 'Users', minRole: 'admin' },
]

export function Layout() {
  const me = useMe()
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => api<null>('/auth/logout', { method: 'POST' }),
    onSettled: () => {
      queryClient.clear()
      window.location.assign('/')
    },
  })

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">BVT MDM</span>
        <nav aria-label="Main">
          {NAV.filter((n) => !n.minRole || hasRole(me, n.minRole)).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="user-menu">
          <span className="user-email" title={me.email}>
            {me.display_name ?? me.email}
          </span>
          <span className={`badge badge-${me.role}`}>{me.role}</span>
          <button
            type="button"
            className="btn"
            disabled={logout.isPending}
            onClick={() => {
              logout.mutate()
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

export function ComingSoon({ title }: { title: string }) {
  return (
    <section>
      <h1>{title}</h1>
      <p className="muted">Not built yet.</p>
    </section>
  )
}

export function Forbidden() {
  return (
    <section>
      <h1>Not allowed</h1>
      <p className="muted">Your role doesn&apos;t give access to this page.</p>
    </section>
  )
}
