import { expect, type Page } from '@playwright/test'

export const uid = () =>
  Date.now().toString(36).toUpperCase().slice(-5) + String(Math.floor(Math.random() * 90 + 10))

export interface PartnerData {
  code: string
  legal: string
  trade?: string
  eori?: string
  country: string
  currency?: string
  status?: 'active' | 'on_hold' | 'blocked'
  terms?: string
  incoterm?: string
  leadTime?: string
}

type Kind = 'customer' | 'vendor'
const path = (kind: Kind) => (kind === 'customer' ? '/customers' : '/vendors')

export async function fillPartner(page: Page, dialogTitle: string, d: Partial<PartnerData>) {
  const f = page.getByRole('dialog', { name: dialogTitle })
  if (d.code !== undefined) await f.getByLabel('Code').fill(d.code)
  if (d.legal !== undefined) await f.getByLabel('Legal name').fill(d.legal)
  if (d.trade !== undefined) await f.getByLabel('Trade name').fill(d.trade)
  if (d.eori !== undefined) await f.getByLabel('EORI').fill(d.eori)
  if (d.country) await f.getByLabel('Country').selectOption(d.country)
  if (d.currency) await f.getByLabel('Default currency').selectOption(d.currency)
  if (d.status) await f.getByLabel('Status').selectOption(d.status)
  if (d.terms !== undefined) await f.getByLabel('Payment terms').selectOption(d.terms)
  if (d.incoterm !== undefined) await f.getByLabel('Incoterm').selectOption(d.incoterm)
  if (d.leadTime !== undefined) await f.getByLabel('Lead time (days)').fill(d.leadTime)
  return f
}

export async function addPartner(page: Page, kind: Kind, d: PartnerData): Promise<void> {
  await page.goto(path(kind))
  await page.getByRole('button', { name: `Add ${kind}` }).click()
  const f = await fillPartner(page, `Add ${kind}`, d)
  await f.getByRole('button', { name: `Add ${kind}` }).click()
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(escape(d.legal)) })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText(`${d.legal} added.`)
}

export async function openPartner(page: Page, kind: Kind, code: string, record: 'true' | 'false' | '' = 'true') {
  await page.goto(path(kind))
  await page.getByRole('combobox', { name: 'Filter by record' }).selectOption(record)
  await page.getByRole('searchbox', { name: `Search ${kind}s` }).fill(code)
  await page.getByRole('row', { name: new RegExp(`^${escape(code)} `) }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Identity and terms' })).toBeVisible()
}

export async function addAddress(page: Page, type: string, city: string) {
  await page.getByRole('button', { name: 'Add address' }).click()
  const d = page.getByRole('dialog', { name: 'Add address' })
  await d.getByLabel('Type').selectOption(type)
  await d.getByLabel('Address line 1').fill(`${city} street 1`)
  await d.getByLabel('City').fill(city)
  await d.getByLabel('Country').selectOption('MX')
  await d.getByRole('button', { name: 'Add address' }).click()
  await expect(d).toBeHidden()
}

export async function confirmIn(page: Page, dialog: string, button = 'Remove') {
  await page.getByRole('dialog', { name: dialog }).getByRole('button', { name: button }).click()
}

export const identity = (page: Page) => page.getByRole('region', { name: 'Identity and terms' })
export const rowsOf = (page: Page, table: string) =>
  page.getByRole('table', { name: table }).locator('tbody tr')

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
