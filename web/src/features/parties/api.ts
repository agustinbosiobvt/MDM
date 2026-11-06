// Addresses and contacts belong to a party (a company now; customers and vendors later).
import { api, query } from '../../api/client'

export type AddressType = 'registered' | 'billing' | 'warehouse' | 'shipping' | 'pickup' | 'factory'

export const ADDRESS_TYPE_LABELS: Record<AddressType, string> = {
  registered: 'Registered office',
  billing: 'Billing',
  warehouse: 'Warehouse',
  shipping: 'Ship-to',
  pickup: 'Pick-up',
  factory: 'Factory',
}

export type ContactRole = 'sales' | 'logistics' | 'quality' | 'other'

export const CONTACT_ROLE_LABELS: Record<ContactRole, string> = {
  sales: 'Sales',
  logistics: 'Logistics',
  quality: 'Quality',
  other: 'Other',
}

export interface Address {
  id: string
  party_id: string
  address_type: AddressType
  line1: string
  line2: string | null
  postal_code: string | null
  city: string
  region: string | null
  country_code: string
  version: number
}

export type AddressInput = Omit<Address, 'id' | 'party_id' | 'version'>

export interface Contact {
  id: string
  party_id: string
  name: string
  role_title: string | null
  email: string | null
  phone: string | null
  is_primary: boolean
  contact_role: ContactRole | null
  version: number
}

export type ContactInput = Omit<Contact, 'id' | 'party_id' | 'version'>

const json = (body: unknown) => JSON.stringify(body)

export const addAddress = (partyId: string, body: AddressInput) =>
  api<Address>(`/api/parties/${partyId}/addresses`, { method: 'POST', body: json(body) })
export const updateAddress = (a: Address, body: AddressInput) =>
  api<Address>(`/api/addresses/${a.id}`, { method: 'PATCH', body: json({ ...body, version: a.version }) })
export const removeAddress = (a: Address) =>
  api<null>(`/api/addresses/${a.id}${query({ version: a.version })}`, { method: 'DELETE' })

export const addContact = (partyId: string, body: ContactInput) =>
  api<Contact>(`/api/parties/${partyId}/contacts`, { method: 'POST', body: json(body) })
export const updateContact = (c: Contact, body: ContactInput) =>
  api<Contact>(`/api/contacts/${c.id}`, { method: 'PATCH', body: json({ ...body, version: c.version }) })
export const removeContact = (c: Contact) =>
  api<null>(`/api/contacts/${c.id}${query({ version: c.version })}`, { method: 'DELETE' })

export function formatAddress(a: Address): string {
  return [a.line1, a.line2, [a.postal_code, a.city].filter(Boolean).join(' '), a.region]
    .filter(Boolean)
    .join(', ')
}
