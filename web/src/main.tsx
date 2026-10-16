import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { ComingSoon, Layout } from './components/Layout'
import { HomePage } from './features/home/HomePage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'company', element: <ComingSoon title="Company" /> },
      { path: 'customers', element: <ComingSoon title="Customers" /> },
      { path: 'vendors', element: <ComingSoon title="Vendors" /> },
      { path: 'price-lists', element: <ComingSoon title="Price lists" /> },
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
