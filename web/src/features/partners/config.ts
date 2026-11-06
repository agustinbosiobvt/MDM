import type { AddressType } from '../parties/api'

export type PartnerKind = 'customer' | 'vendor'
export type PartnerStatus = 'active' | 'on_hold' | 'blocked'

export const STATUS_LABELS: Record<PartnerStatus, string> = {
  active: 'Active',
  on_hold: 'On hold',
  blocked: 'Blocked',
}

export interface PartnerConfig {
  kind: PartnerKind
  path: string // UI route
  api: string // API prefix
  title: string // "Customers"
  singular: string // "Customer"
  intro: string
  addressTypes: AddressType[]
  hasEori: boolean
  hasLeadTime: boolean
  hasVendorCodes: boolean
  contactRoles: boolean
}

export const CUSTOMERS: PartnerConfig = {
  kind: 'customer',
  path: '/customers',
  api: '/api/customers',
  title: 'Customers',
  singular: 'Customer',
  intro: 'Who BVT sells to (e.g. Amazon MX, Amazon US).',
  addressTypes: ['billing', 'shipping'],
  hasEori: false,
  hasLeadTime: false,
  hasVendorCodes: true,
  contactRoles: false,
}

export const VENDORS: PartnerConfig = {
  kind: 'vendor',
  path: '/vendors',
  api: '/api/vendors',
  title: 'Vendors',
  singular: 'Vendor',
  intro: 'Brands and manufacturers BVT buys from (e.g. Nobby).',
  addressTypes: ['billing', 'pickup', 'factory'],
  hasEori: true,
  hasLeadTime: true,
  hasVendorCodes: false,
  contactRoles: true,
}
