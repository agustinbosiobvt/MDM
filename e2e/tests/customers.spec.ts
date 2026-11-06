import { expect, test } from '@playwright/test'
import { ADMIN, signInExpectingSuccess } from './helpers'
import {
  addAddress,
  addPartner,
  confirmIn,
  fillPartner,
  identity,
  openPartner,
  rowsOf,
  uid,
} from './partner-helpers'

test.describe('Customers', () => {
  test.beforeEach(async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
  })

  test('add, view, edit, remove — with addresses, contacts and Amazon vendor codes', async ({ page }) => {
    const id = uid()
    const c = {
      code: `AMZ-MX-${id}`,
      legal: `Servicios Comerciales Amazon México ${id}`,
      trade: 'Amazon MX',
      country: 'MX',
      currency: 'MXN',
      terms: 'NET60',
      incoterm: 'DDP',
    }
    await addPartner(page, 'customer', c)

    // View
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Active')
    await expect(identity(page)).toContainText('Mexico (MX)')
    await expect(identity(page)).toContainText('MXN')
    await expect(identity(page)).toContainText('Net 60 days (NET60)')
    await expect(identity(page)).toContainText('Delivered Duty Paid (DDP)')
    await expect(identity(page)).not.toContainText('EORI') // customers have none

    // Edit: business status and terms
    await page.getByRole('button', { name: 'Edit customer' }).click()
    const edit = await fillPartner(page, 'Edit customer', { status: 'on_hold', incoterm: 'FOB', terms: '' })
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toHaveText('Customer saved.')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('On hold')
    await expect(identity(page)).toContainText('Free on Board (FOB)')
    await expect(identity(page)).toContainText(/Payment terms\s*—/)

    // Addresses: billing + several ship-to; the type list is customer-specific.
    await page.getByRole('button', { name: 'Add address' }).click()
    const types = await page.getByRole('dialog', { name: 'Add address' }).getByLabel('Type').locator('option').allTextContents()
    expect(types).toEqual(['Billing', 'Ship-to'])
    await page.getByRole('dialog', { name: 'Add address' }).getByRole('button', { name: 'Close' }).click()
    await addAddress(page, 'billing', 'Ciudad de Mexico')
    await addAddress(page, 'shipping', 'Guadalajara')
    await addAddress(page, 'shipping', 'Monterrey')
    await expect(rowsOf(page, 'Addresses')).toHaveCount(3)
    await page.getByRole('row', { name: /Ship-to: Monterrey/ }).getByRole('button', { name: 'Remove' }).click()
    await confirmIn(page, 'Remove address')
    await expect(rowsOf(page, 'Addresses')).toHaveCount(2)

    // Contacts (free-text job title, no role list for customers)
    await page.getByRole('button', { name: 'Add contact' }).click()
    const cd = page.getByRole('dialog', { name: 'Add contact' })
    await expect(cd.getByLabel('Contact role')).toHaveCount(0)
    await cd.getByLabel('Name').fill('Vendor Manager MX')
    await cd.getByLabel('Job title').fill('Vendor manager')
    await cd.getByRole('button', { name: 'Add contact' }).click()
    await expect(page.getByRole('row', { name: 'Vendor Manager MX' })).toContainText('Primary')

    // Amazon vendor codes: several pairs; normalised; edit; remove.
    for (const [parent, child] of [[`p${id}`, `c${id}a`], [`p${id}`, `c${id}b`]]) {
      await page.getByRole('button', { name: 'Add vendor code' }).click()
      const vd = page.getByRole('dialog', { name: 'Add vendor code' })
      await vd.getByLabel('Parent vendor code').fill(parent ?? '')
      await vd.getByLabel('Child vendor code').fill(child ?? '')
      await vd.getByLabel('Destination country').selectOption('MX')
      await vd.getByRole('button', { name: 'Add vendor code' }).click()
      await expect(vd).toBeHidden()
    }
    await expect(rowsOf(page, 'Vendor codes')).toHaveCount(2)
    const first = page.getByRole('row', { name: `P${id} / C${id}A` }) // upper-cased
    await expect(first).toContainText('MX')
    await first.getByRole('button', { name: 'Edit' }).click()
    const ve = page.getByRole('dialog', { name: 'Edit vendor code' })
    await expect(ve.getByLabel('Description')).toHaveCount(0) // field removed
    await ve.getByLabel('Destination country').selectOption('US')
    await ve.getByRole('button', { name: 'Save vendor code' }).click()
    await expect(page.getByRole('row', { name: `P${id} / C${id}A` })).toContainText('US')
    await page.getByRole('row', { name: `P${id} / C${id}B` }).getByRole('button', { name: 'Remove' }).click()
    await confirmIn(page, 'Remove vendor code')
    await expect(rowsOf(page, 'Vendor codes')).toHaveCount(1)

    // The same pair can't be given to another customer.
    await addPartner(page, 'customer', { code: `AMZ-US-${id}`, legal: `Amazon US ${id}`, country: 'US', currency: 'USD' })
    await page.getByRole('button', { name: 'Add vendor code' }).click()
    const dup = page.getByRole('dialog', { name: 'Add vendor code' })
    await dup.getByLabel('Parent vendor code').fill(`P${id}`)
    await dup.getByLabel('Child vendor code').fill(`C${id}A`)
    await dup.getByRole('button', { name: 'Add vendor code' }).click()
    await expect(dup.getByRole('alert')).toHaveText('This parent/child vendor code pair is already assigned')
    await dup.getByRole('button', { name: 'Close' }).click()

    // Remove (soft) → reactivate → remove → Admin deletes permanently.
    await openPartner(page, 'customer', c.code)
    await page.getByRole('button', { name: 'Remove customer' }).click()
    await confirmIn(page, 'Remove customer')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Removed')
    await expect(page.getByRole('button', { name: 'Add vendor code' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Reactivate' }).click()
    await expect(page.getByRole('status')).toHaveText(`${c.legal} reactivated.`)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('On hold') // business status kept
    await page.getByRole('button', { name: 'Remove customer' }).click()
    await confirmIn(page, 'Remove customer')
    await page.getByRole('button', { name: 'Delete permanently' }).click()
    const del = page.getByRole('dialog', { name: 'Delete customer permanently' })
    await del.getByLabel(`Type ${c.code} to confirm`).fill(c.code)
    await del.getByRole('button', { name: 'Delete permanently' }).click()
    await expect(page).toHaveURL(/\/customers$/)
    await expect(page.getByRole('status')).toHaveText(`${c.legal} was deleted permanently.`)
  })

  test('list: search, business-status filter, sort', async ({ page }) => {
    const id = uid()
    await addPartner(page, 'customer', { code: `LS-A-${id}`, legal: `Alpha Retail ${id}`, country: 'US', status: 'active' })
    await addPartner(page, 'customer', { code: `LS-B-${id}`, legal: `Beta Retail ${id}`, country: 'US', status: 'blocked' })
    await page.goto('/customers')
    await page.getByRole('searchbox', { name: 'Search customers' }).fill(id)
    const rows = page.locator('table.data-table tbody tr')
    await expect(rows).toHaveCount(2)
    await page.getByRole('combobox', { name: 'Filter by business status' }).selectOption('blocked')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Blocked')
    await page.getByRole('combobox', { name: 'Filter by business status' }).selectOption('')
    await page.getByRole('button', { name: 'Legal name' }).click() // → desc
    await expect(rows.first()).toContainText('Beta Retail')
  })

  test('two people editing the same customer: the second save is refused', async ({ page, browser }) => {
    const id = uid()
    const c = { code: `CF-${id}`, legal: `Conflict Customer ${id}`, country: 'MX' }
    await addPartner(page, 'customer', c)
    await page.getByRole('button', { name: 'Edit customer' }).click()

    const ctx = await browser.newContext()
    const other = await ctx.newPage()
    await signInExpectingSuccess(other, ADMIN)
    await openPartner(other, 'customer', c.code)
    await other.getByRole('button', { name: 'Edit customer' }).click()
    const o = await fillPartner(other, 'Edit customer', { status: 'blocked' })
    await o.getByRole('button', { name: 'Save changes' }).click()
    await expect(other.getByRole('status')).toHaveText('Customer saved.')
    await ctx.close()

    const d = await fillPartner(page, 'Edit customer', { trade: 'Stale' })
    await d.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toContainText('Someone else changed this record')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Blocked')
  })
})
