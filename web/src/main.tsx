import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { ApiError } from './api/client'
import { RequireAuth } from './auth/AuthProvider'
import { ComingSoon, Layout } from './components/Layout'
import { RoleGate } from './components/RoleGate'
import { CompaniesPage } from './features/company/CompaniesPage'
import { ImportWizardPage } from './features/imports/ImportWizardPage'
import { CompanyDetailPage } from './features/company/CompanyDetailPage'
import { NoAccessPage } from './features/auth/NoAccessPage'
import { HomePage } from './features/home/HomePage'
import { CUSTOMERS, VENDORS } from './features/partners/config'
import { PartnerDetailPage } from './features/partners/PartnerDetailPage'
import { PartnersPage } from './features/partners/PartnersPage'
import { UsersPage } from './features/users/UsersPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Don't retry auth/permission/validation errors.
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
})

const router = createBrowserRouter([
  { path: '/no-access', element: <NoAccessPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: 'company', element: <CompaniesPage /> },
      { path: 'company/:id', element: <CompanyDetailPage /> },
      // key= remounts the shared page when switching between customers and vendors.
      { path: 'customers', element: <PartnersPage key="customers" cfg={CUSTOMERS} /> },
      { path: 'customers/:id', element: <PartnerDetailPage key="customer" cfg={CUSTOMERS} /> },
      { path: 'vendors', element: <PartnersPage key="vendors" cfg={VENDORS} /> },
      { path: 'vendors/:id', element: <PartnerDetailPage key="vendor" cfg={VENDORS} /> },
      {
        path: 'customers/:id/import',
        element: (
          <RoleGate min="editor">
            <ImportWizardPage key="customer-import" cfg={CUSTOMERS} />
          </RoleGate>
        ),
      },
      {
        path: 'vendors/:id/import',
        element: (
          <RoleGate min="editor">
            <ImportWizardPage key="vendor-import" cfg={VENDORS} />
          </RoleGate>
        ),
      },
      {
        path: 'users',
        element: (
          <RoleGate min="admin">
            <UsersPage />
          </RoleGate>
        ),
      },
      { path: '*', element: <ComingSoon title="Not found" /> },
    ],
  },
])

const root = document.getElementById('root')
if (!root) throw new Error('#root missing')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
