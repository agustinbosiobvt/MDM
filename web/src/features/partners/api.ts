import { api, query, type Page } from '../../api/client'
import type { Address, Contact } from '../parties/api'
import type { PartnerConfig, PartnerStatus } from './config'

export interface Partner {
  id: string
  code: string
  legal_name: string
  trade_name: string | null
  eori?: string | null // vendors
  country_code: string
  default_currency: string
  status: PartnerStatus
  payment_term_code: string | null
  incoterm_code: string | null
  lead_time_days?: number | null // vendors
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface VendorCode {
  id: string
  customer_id: string
  parent_code: string
  child_code: string
  destination_country: string | null
  version: number
}

export type VendorCodeInput = Omit<VendorCode, 'id' | 'customer_id' | 'version'>

export interface PartnerDetail extends Partner {
  addresses: Address[]
  contacts: Contact[]
  vendor_codes?: VendorCode[] // customers
}

export interface PartnerInput {
  code: string
  legal_name: string
  trade_name: string | null
  country_code: string
  default_currency: string
  status: PartnerStatus
  payment_term_code: string | null
  incoterm_code: string | null
  eori?: string | null
  lead_time_days?: number | null
}

export interface PartnerListParams {
  q?: string
  active?: '' | 'true' | 'false'
  status?: '' | PartnerStatus
  sort: string
  order: 'asc' | 'desc'
  page: number
  page_size: number
}

const json = (body: unknown) => JSON.stringify(body)

export const partnerApi = (cfg: PartnerConfig) => ({
  list: (p: PartnerListParams) => api<Page<Partner>>(`${cfg.api}${query({ ...p })}`),
  get: (id: string) => api<PartnerDetail>(`${cfg.api}/${id}`),
  create: (body: PartnerInput) => api<PartnerDetail>(cfg.api, { method: 'POST', body: json(body) }),
  update: (p: Partner, body: Partial<PartnerInput> & { is_active?: boolean }) =>
    api<PartnerDetail>(`${cfg.api}/${p.id}`, {
      method: 'PATCH',
      body: json({ ...body, version: p.version }),
    }),
  remove: (p: Partner) =>
    api<Partner>(`${cfg.api}/${p.id}${query({ version: p.version })}`, { method: 'DELETE' }),
  deletePermanently: (p: Partner, confirm: string) =>
    api<null>(`${cfg.api}/${p.id}/permanent${query({ confirm })}`, { method: 'DELETE' }),
})

export const addVendorCode = (customerId: string, body: VendorCodeInput) =>
  api<VendorCode>(`/api/customers/${customerId}/vendor-codes`, { method: 'POST', body: json(body) })
export const updateVendorCode = (v: VendorCode, body: VendorCodeInput) =>
  api<VendorCode>(`/api/vendor-codes/${v.id}`, {
    method: 'PATCH',
    body: json({ ...body, version: v.version }),
  })
export const removeVendorCode = (v: VendorCode) =>
  api<null>(`/api/vendor-codes/${v.id}${query({ version: v.version })}`, { method: 'DELETE' })
