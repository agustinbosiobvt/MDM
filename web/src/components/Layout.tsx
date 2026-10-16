import { NavLink, Outlet } from 'react-router'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/company', label: 'Company' },
  { to: '/customers', label: 'Customers' },
  { to: '/vendors', label: 'Vendors' },
  { to: '/price-lists', label: 'Price lists' },
]

export function Layout() {
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">BVT MDM</span>
        <nav>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
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
