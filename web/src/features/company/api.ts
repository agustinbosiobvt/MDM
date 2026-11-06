import { api, query, type Page } from '../../api/client'
import type { Address, Contact } from '../parties/api'

export interface Company {
  id: string
  code: string
  legal_name: string
  trade_name: string | null
  eori: string | null
  country_code: string
  tax_registration_number: string | null
  is_default: boolean
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface CompanyDetail extends Company {
  addresses: Address[]
  contacts: Contact[]
}

export interface CompanyInput {
  code: string
  legal_name: string
  trade_name: string | null
  eori: string | null
  country_code: string
  tax_registration_number: string | null
}

export interface CompanyListParams {
  q?: string
  active?: '' | 'true' | 'false'
  sort: string
  order: 'asc' | 'desc'
  page: number
  page_size: number
}

const json = (body: unknown) => JSON.stringify(body)

export const listCompanies = (p: CompanyListParams) =>
  api<Page<Company>>(`/api/companies${query({ ...p })}`)
export const getCompany = (id: string) => api<CompanyDetail>(`/api/companies/${id}`)
export const createCompany = (body: CompanyInput) =>
  api<CompanyDetail>('/api/companies', { method: 'POST', body: json(body) })
export const updateCompany = (c: Company, body: Partial<CompanyInput> & { is_active?: boolean }) =>
  api<CompanyDetail>(`/api/companies/${c.id}`, {
    method: 'PATCH',
    body: json({ ...body, version: c.version }),
  })
export const makeDefault = (c: Company) =>
  api<CompanyDetail>(`/api/companies/${c.id}/default`, { method: 'POST' })
export const removeCompany = (c: Company) =>
  api<Company>(`/api/companies/${c.id}${query({ version: c.version })}`, { method: 'DELETE' })
export const deletePermanently = (c: Company, confirm: string) =>
  api<null>(`/api/companies/${c.id}/permanent${query({ confirm })}`, { method: 'DELETE' })
