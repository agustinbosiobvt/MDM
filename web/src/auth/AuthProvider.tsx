import { useEffect, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, UNAUTHENTICATED_EVENT } from '../api/client'
import { AuthContext, type Me } from './context'
import { LoginPage } from '../features/auth/LoginPage'

/** Renders children only for a signed-in user; otherwise the login page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Me>('/api/me'),
    retry: false,
    staleTime: 60_000,
  })

  // Any 401 from another call means the session ended: re-check /api/me.
  useEffect(() => {
    const onUnauth = () => void queryClient.invalidateQueries({ queryKey: ['me'] })
    window.addEventListener(UNAUTHENTICATED_EVENT, onUnauth)
    return () => {
      window.removeEventListener(UNAUTHENTICATED_EVENT, onUnauth)
    }
  }, [queryClient])

  if (me.isPending) return <p className="centered muted">Loading…</p>
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <LoginPage />
    return <p className="centered error">The server is unreachable. Try again in a moment.</p>
  }
  return <AuthContext.Provider value={me.data}>{children}</AuthContext.Provider>
}
