import { createContext, useContext } from 'react'

export type Role = 'admin' | 'editor' | 'viewer'

export interface Me {
  id: string
  email: string
  display_name: string | null
  role: Role
}

export const AuthContext = createContext<Me | null>(null)

export function useMe(): Me {
  const me = useContext(AuthContext)
  if (!me) throw new Error('useMe() outside <RequireAuth>')
  return me
}

const RANK: Record<Role, number> = { viewer: 1, editor: 2, admin: 3 }

/** UI convenience only: the server checks every request. */
export function hasRole(me: Me, minimum: Role): boolean {
  return RANK[me.role] >= RANK[minimum]
}
