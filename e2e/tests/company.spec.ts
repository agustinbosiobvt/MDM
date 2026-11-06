import { expect, test, type Page } from '@playwright/test'
import { ADMIN, addUser, signInExpectingSuccess, uniqueEmail } from './helpers'

interface CompanyData {
  code: string
  legal: string
  trade?: string
  eori?: string
  country?: string
}

const uid = () => Date.now().toString(36).toUpperCase().slice(-5) + String(Math.floor(Math.random() * 90 + 10))

async function addCompany(page: Page, c: CompanyData): Promise<void> {
  await page.goto('/company')
  await page.getByRole('button', { name: 'Add company' }).click()
  const d = page.getByRole('dialog', { name: 'Add company' })
  await d.getByLabel('Code').fill(c.code)
  await d.getByLabel('Legal name').fill(c.legal)
  if (c.trade) await d.getByLabel('Trade name').fill(c.trade)
  if (c.eori) await d.getByLabel('EORI').fill(c.eori)
  await d.getByLabel('Country').selectOption(c.country ?? 'ES')
  await d.getByRole('button', { name: 'Add company' }).click()
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(c.legal) })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText(`${c.legal} added.`)
}

async function openCompany(page: Page, code: string, status: 'true' | 'false' | '' = 'true') {
  await page.goto('/company')
  await page.getByRole('combobox', { name: 'Filter by status' }).selectOption(status)
  await page.getByRole('searchbox', { name: 'Search companies' }).fill(code)
  await page.getByRole('row', { name: new RegExp(`^${code} `) }).click()
}

const identity = (page: Page) => page.getByRole('region', { name: 'Identity' })
const addresses = (page: Page) => page.getByRole('table', { name: 'Addresses' }).locator('tbody tr')
const contacts = (page: Page) => page.getByRole('table', { name: 'Contacts' }).locator('tbody tr')

async function fillAddress(page: Page, title: string, a: Record<string, string>) {
  const d = page.getByRole('dialog', { name: title })
  if (a.type) await d.getByLabel('Type').selectOption(a.type)
  if (a.line1 !== undefined) await d.getByLabel('Address line 1').fill(a.line1)
  if (a.postal !== undefined) await d.getByLabel('Postal code').fill(a.postal)
  if (a.city !== undefined) await d.getByLabel('City').fill(a.city)
  if (a.country) await d.getByLabel('Country').selectOption(a.country)
  await d.getByRole('button', { name: /Add address|Save address/ }).click()
  await expect(d).toBeHidden() // the same notice text repeats, so wait for the dialog itself
}

async function addContact(page: Page, name: string, extra: { role?: string; email?: string; phone?: string } = {}) {
  await page.getByRole('button', { name: 'Add contact' }).click()
  const d = page.getByRole('dialog', { name: 'Add contact' })
  await d.getByLabel('Name').fill(name)
  if (extra.role) await d.getByLabel('Job title').fill(extra.role)
  if (extra.email) await d.getByLabel('Email').fill(extra.email)
  if (extra.phone) await d.getByLabel('Phone').fill(extra.phone)
  await d.getByRole('button', { name: 'Add contact' }).click()
  await expect(d).toBeHidden()
  await expect(page.getByRole('status')).toHaveText('Contact added.')
}

test.describe('Company', () => {
  test('add, view, edit, remove — with addresses, contacts and the default company', async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    const a = { code: `BVT-${id}`, legal: `Buena Vida Trading ${id} S.L.`, trade: 'Buena Vida', eori: `es b${id}` }
    await addCompany(page, a)

    // View: identity as entered, normalised where the rules say so.
    await expect(identity(page)).toContainText(a.code)
    await expect(identity(page)).toContainText(`ESB${id}`) // EORI upper-cased, spaces removed
    await expect(identity(page)).toContainText('Spain (ES)')
    await expect(identity(page)).not.toContainText(/currency|Tax ID/i) // removed from the spec

    // Edit identity.
    await page.getByRole('button', { name: 'Edit company' }).click()
    const edit = page.getByRole('dialog', { name: 'Edit company' })
    await edit.getByLabel('Trade name').fill('BVT Iberia')
    await edit.getByLabel('Country').selectOption('PT')
    await edit.getByLabel('Tax registration number').fill('TRN 104965266000001')
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toHaveText('Company saved.')
    await expect(identity(page)).toContainText('BVT Iberia')
    await expect(identity(page)).toContainText('Portugal (PT)')
    await expect(identity(page)).toContainText('TRN 104965266000001')

    // Addresses: registered, billing, warehouse; edit one; remove one.
    const kinds: [string, string][] = [['registered', 'Madrid'], ['billing', 'Valencia'], ['warehouse', 'Zaragoza']]
    for (const [type, city] of kinds) {
      await page.getByRole('button', { name: 'Add address' }).click()
      await fillAddress(page, 'Add address', { type, line1: `Calle ${city} 1`, postal: '28001', city, country: 'ES' })
      await expect(page.getByRole('status')).toHaveText('Address added.')
    }
    await expect(addresses(page)).toHaveCount(3)
    const billing = page.getByRole('row', { name: /^Billing:/ })
    await billing.getByRole('button', { name: 'Edit' }).click()
    await fillAddress(page, 'Edit address', { city: 'Barcelona' })
    await expect(page.getByRole('status')).toHaveText('Address saved.')
    await expect(page.getByRole('row', { name: /^Billing:/ })).toContainText('Barcelona')
    await page.getByRole('row', { name: /^Warehouse:/ }).getByRole('button', { name: 'Remove' }).click()
    await page.getByRole('dialog', { name: 'Remove address' }).getByRole('button', { name: 'Remove' }).click()
    await expect(page.getByRole('status')).toHaveText('Address removed.')
    await expect(addresses(page)).toHaveCount(2)

    // Contacts: the first is primary; switch primary; edit; remove.
    await addContact(page, 'Ana García', { role: 'CEO', email: 'Ana@BuenaVidaTrading.com', phone: '+34 600 000 001' })
    await expect(page.getByRole('row', { name: 'Ana García' })).toContainText('Primary')
    await expect(page.getByRole('row', { name: 'Ana García' })).toContainText('ana@buenavidatrading.com')
    await addContact(page, 'Bob Ruiz')
    await expect(page.getByRole('row', { name: 'Bob Ruiz' })).not.toContainText('Primary')
    await page.getByRole('row', { name: 'Bob Ruiz' }).getByRole('button', { name: 'Make primary' }).click()
    await expect(page.getByRole('status')).toHaveText('Bob Ruiz is now the primary contact.')
    await expect(page.getByRole('row', { name: 'Bob Ruiz' })).toContainText('Primary')
    await expect(page.getByRole('row', { name: 'Ana García' })).not.toContainText('Primary')
    await page.getByRole('row', { name: 'Ana García' }).getByRole('button', { name: 'Edit' }).click()
    const ce = page.getByRole('dialog', { name: 'Edit contact' })
    await ce.getByLabel('Job title').fill('Managing director')
    await ce.getByRole('button', { name: 'Save contact' }).click()
    await expect(page.getByRole('row', { name: 'Ana García' })).toContainText('Managing director')
    await page.getByRole('row', { name: 'Bob Ruiz' }).getByRole('button', { name: 'Remove' }).click()
    await page.getByRole('dialog', { name: 'Remove contact' }).getByRole('button', { name: 'Remove' }).click()
    await expect(contacts(page)).toHaveCount(1)

    // Default company: it can't be removed until another company is the default.
    if (await page.getByRole('button', { name: 'Make default' }).isVisible()) {
      await page.getByRole('button', { name: 'Make default' }).click()
    }
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Default')
    await expect(page.getByRole('button', { name: 'Remove company' })).toBeDisabled()
    const b = { code: `BVT2-${id}`, legal: `BVT Second ${id} GmbH`, country: 'DE' }
    await addCompany(page, b)
    await page.getByRole('button', { name: 'Make default' }).click()
    await expect(page.getByRole('status')).toHaveText(`${b.legal} is now the default company.`)

    // Remove (soft) → shown as Removed, hidden from the active list, reactivatable.
    await openCompany(page, a.code)
    await expect(page.getByRole('heading', { level: 1 })).not.toContainText('Default')
    await page.getByRole('button', { name: 'Remove company' }).click()
    await page.getByRole('dialog', { name: 'Remove company' }).getByRole('button', { name: 'Remove' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Removed')
    await expect(page.getByRole('button', { name: 'Add address' })).toHaveCount(0) // read-only while removed
    await page.goto('/company')
    await page.getByRole('searchbox', { name: 'Search companies' }).fill(a.code)
    await expect(page.getByText('No companies match.')).toBeVisible()
    await openCompany(page, a.code, 'false')
    await page.getByRole('button', { name: 'Reactivate' }).click()
    await expect(page.getByRole('status')).toHaveText(`${a.legal} reactivated.`)

    // Admin: permanent delete needs a removed company and the code typed in.
    await page.getByRole('button', { name: 'Remove company' }).click()
    await page.getByRole('dialog', { name: 'Remove company' }).getByRole('button', { name: 'Remove' }).click()
    await page.getByRole('button', { name: 'Delete permanently' }).click()
    const del = page.getByRole('dialog', { name: 'Delete company permanently' })
    await expect(del.getByRole('button', { name: 'Delete permanently' })).toBeDisabled()
    await del.getByLabel(`Type ${a.code} to confirm`).fill(a.code.toLowerCase())
    await del.getByRole('button', { name: 'Delete permanently' }).click()
    await expect(page).toHaveURL(/\/company$/)
    await expect(page.getByRole('status')).toHaveText(`${a.legal} was deleted permanently.`)
    await page.getByRole('combobox', { name: 'Filter by status' }).selectOption('')
    await page.getByRole('searchbox', { name: 'Search companies' }).fill(a.code)
    await expect(page.getByRole('row', { name: new RegExp(`^${a.code} `) })).toHaveCount(0)
  })

  test('list: search, sort and status filter', async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    await addCompany(page, { code: `LA-${id}`, legal: `Aardvark ${id} Ltd`, country: 'GB' })
    await addCompany(page, { code: `LZ-${id}`, legal: `Zebra ${id} Ltd`, country: 'GB' })
    await page.goto('/company')
    await page.getByRole('searchbox', { name: 'Search companies' }).fill(id)
    const rows = page.locator('table.data-table tbody tr')
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('Aardvark')
    await page.getByRole('button', { name: 'Legal name' }).click() // asc → desc
    await expect(rows.first()).toContainText('Zebra')
    await page.getByRole('searchbox', { name: 'Search companies' }).fill(`LZ-${id}`) // by code
    await expect(rows).toHaveCount(1)
  })

  test('validation errors and duplicate code', async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    await addCompany(page, { code: `DUP-${id}`, legal: `Original ${id}` })

    await page.goto('/company')
    await page.getByRole('button', { name: 'Add company' }).click()
    const d = page.getByRole('dialog', { name: 'Add company' })
    await d.getByRole('button', { name: 'Add company' }).click()
    await expect(d.getByText('Legal name is required')).toBeVisible()
    await expect(d.getByText('Choose a country')).toBeVisible()

    await d.getByLabel('Code').fill(`DUP-${id}`)
    await d.getByLabel('Legal name').fill('Copycat')
    await d.getByLabel('EORI').fill('123')
    await d.getByLabel('Country').selectOption('ES')
    await d.getByRole('button', { name: 'Add company' }).click()
    await expect(d.getByText(/Country code \+ up to 15/)).toBeVisible()

    await d.getByLabel('EORI').fill('')
    await d.getByRole('button', { name: 'Add company' }).click()
    await expect(d.getByRole('alert')).toHaveText('Another record already uses this code')
  })

  test('a viewer can read companies but not change them', async ({ page, browser }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    const viewer = uniqueEmail('company.viewer')
    await addUser(page, viewer, 'viewer')
    await addCompany(page, { code: `RO-${id}`, legal: `Read Only ${id}` })
    await page.getByRole('button', { name: 'Add address' }).click()
    await fillAddress(page, 'Add address', { type: 'registered', line1: 'Main St 1', city: 'Madrid', country: 'ES' })
    await expect(addresses(page)).toHaveCount(1)
    const companyUrl = page.url()

    const ctx = await browser.newContext()
    const v = await ctx.newPage()
    await signInExpectingSuccess(v, viewer)
    await v.goto('/company')
    await expect(v.getByRole('button', { name: 'Add company' })).toHaveCount(0)
    await v.goto(companyUrl)
    await expect(v.getByRole('heading', { level: 1 })).toContainText(`Read Only ${id}`)
    await expect(addresses(v)).toHaveCount(1)
    for (const name of ['Edit company', 'Remove company', 'Add address', 'Add contact', 'Edit', 'Remove']) {
      await expect(v.getByRole('button', { name, exact: true })).toHaveCount(0)
    }
    const csrf = (await ctx.cookies()).find((c) => c.name === '__Host-mdm_csrf')?.value ?? ''
    const post = await v.request.post('/api/companies', {
      headers: { 'X-CSRF-Token': csrf, Origin: 'http://localhost:8080' },
      data: { code: `HACK-${id}`, legal_name: 'x', country_code: 'ES' },
    })
    expect(post.status()).toBe(403)
    await ctx.close()
  })

  test('an editor can remove and reactivate, but not delete permanently', async ({ page, browser }) => {
    await signInExpectingSuccess(page, ADMIN)
    const editorEmail = uniqueEmail('company.editor')
    await addUser(page, editorEmail, 'editor')

    const ctx = await browser.newContext()
    const e = await ctx.newPage()
    await signInExpectingSuccess(e, editorEmail)
    const id = uid()
    await addCompany(e, { code: `ED-${id}`, legal: `Editor Made ${id}` })
    if (await e.getByRole('button', { name: 'Remove company' }).isDisabled()) {
      await addCompany(e, { code: `ED2-${id}`, legal: `Editor Default ${id}` })
      await e.getByRole('button', { name: 'Make default' }).click()
      await openCompany(e, `ED-${id}`)
    }
    await e.getByRole('button', { name: 'Remove company' }).click()
    await e.getByRole('dialog', { name: 'Remove company' }).getByRole('button', { name: 'Remove' }).click()
    await expect(e.getByRole('button', { name: 'Reactivate' })).toBeVisible()
    await expect(e.getByRole('button', { name: 'Delete permanently' })).toHaveCount(0)
    await ctx.close()
  })

  test('two people editing the same company: the second save is refused', async ({ page, browser }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    const c = { code: `CF-${id}`, legal: `Conflict ${id} S.A.` }
    await addCompany(page, c)
    await page.getByRole('button', { name: 'Edit company' }).click() // holds version 1

    const ctx = await browser.newContext()
    const other = await ctx.newPage()
    await signInExpectingSuccess(other, ADMIN)
    await openCompany(other, c.code)
    await other.getByRole('button', { name: 'Edit company' }).click()
    await other.getByRole('dialog', { name: 'Edit company' }).getByLabel('Trade name').fill('First wins')
    await other.getByRole('dialog', { name: 'Edit company' }).getByRole('button', { name: 'Save changes' }).click()
    await expect(other.getByRole('status')).toHaveText('Company saved.')
    await ctx.close()

    const d = page.getByRole('dialog', { name: 'Edit company' })
    await d.getByLabel('Trade name').fill('Stale edit')
    await d.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toContainText('Someone else changed this record')
    await expect(identity(page)).toContainText('First wins')
    await expect(identity(page)).not.toContainText('Stale edit')
  })
})
