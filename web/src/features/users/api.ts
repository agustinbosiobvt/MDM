import { api, query, type Page } from '../../api/client'
import type { Role } from '../../auth/context'

export interface User {
  id: string
  email: string
  display_name: string | null
  role: Role
  is_active: boolean
  last_login_at: string | null
  created_at: string
  updated_at: string
  version: number
}

export interface UserListParams {
  q?: string
  role?: Role | ''
  active?: '' | 'true' | 'false'
  sort: string
  order: 'asc' | 'desc'
  page: number
  page_size: number
}

export const listUsers = (p: UserListParams) => api<Page<User>>(`/api/users${query({ ...p })}`)

export const getUser = (id: string) => api<User>(`/api/users/${id}`)

export const createUser = (body: { email: string; role: Role; display_name?: string | null }) =>
  api<User>('/api/users', { method: 'POST', body: JSON.stringify(body) })

export const updateUser = (
  id: string,
  body: { version: number; role?: Role; display_name?: string | null; is_active?: boolean },
) => api<User>(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

export const deactivateUser = (u: User) =>
  api<User>(`/api/users/${u.id}${query({ version: u.version })}`, { method: 'DELETE' })
