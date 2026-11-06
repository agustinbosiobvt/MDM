import type { ReactNode } from 'react'
import { hasRole, useMe, type Role } from '../auth/context'
import { Forbidden } from './Layout'

/** Hides a page from lower roles. UI convenience only: the API enforces every request. */
export function RoleGate({ min, children }: { min: Role; children: ReactNode }) {
  return hasRole(useMe(), min) ? children : <Forbidden />
}
