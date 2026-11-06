import { expect, test } from '@playwright/test'
import { ADMIN, addUser, signInExpectingSuccess, uniqueEmail } from './helpers'
import { addAddress, addPartner, confirmIn, fillPartner, identity, openPartner, rowsOf, uid } from './partner-helpers'

test.describe('Vendors', () => {
  test('add, view, edit, remove — with lead time, addresses and contact roles', async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
    const id = uid()
    const v = {
      code: `NOBBY-${id}`,
      legal: `Nobby Pet Shop ${id} GmbH`,
      eori: `de${id}0001`,
      country: 'DE',
      currency: 'EUR',
      terms: 'NET30',
      incoterm: 'EXW',
      leadTime: '45',
    }
    await addPartner(page, 'vendor', v)
    await expect(identity(page)).toContainText(`DE${id}0001`) // EORI normalised
    await expect(identity(page)).toContainText('45 days')
    await expect(identity(page).getByText('MOQ', { exact: true })).toHaveCount(0)
    await expect(identity(page)).toContainText('Ex Works (EXW)')

    // Lead time validation; MOQ belongs to product lines.
    await page.getByRole('button', { name: 'Edit vendor' }).click()
    const edit = await fillPartner(page, 'Edit vendor', { leadTime: '800' })
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(edit.getByText('Lead time must be at most 730')).toBeVisible()
    await expect(edit.getByLabel('MOQ (units)')).toHaveCount(0)
    await fillPartner(page, 'Edit vendor', { leadTime: '60', status: 'on_hold' })
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toHaveText('Vendor saved.')
    await expect(identity(page)).toContainText('60 days')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('On hold')

    // Addresses: billing / pick-up / factory.
    await page.getByRole('button', { name: 'Add address' }).click()
    const types = await page.getByRole('dialog', { name: 'Add address' }).getByLabel('Type').locator('option').allTextContents()
    expect(types).toEqual(['Billing', 'Pick-up', 'Factory'])
    await page.getByRole('dialog', { name: 'Add address' }).getByRole('button', { name: 'Close' }).click()
    await addAddress(page, 'billing', 'Sassenburg')
    await addAddress(page, 'pickup', 'Hamburg')
    await addAddress(page, 'factory', 'Ningbo')
    await expect(rowsOf(page, 'Addresses')).toHaveCount(3)
    await expect(page.getByRole('row', { name: /^Pick-up: Hamburg/ })).toBeVisible()

    // Contacts with roles: Sales / Logistics / Quality.
    for (const [name, role] of [['Sara Sales', 'sales'], ['Leo Logistics', 'logistics'], ['Quinn Quality', 'quality']]) {
      await page.getByRole('button', { name: 'Add contact' }).click()
      const d = page.getByRole('dialog', { name: 'Add contact' })
      await d.getByLabel('Name').fill(name ?? '')
      await d.getByLabel('Contact role').selectOption(role ?? '')
      await d.getByRole('button', { name: 'Add contact' }).click()
      await expect(d).toBeHidden()
    }
    await expect(page.getByRole('row', { name: 'Sara Sales' })).toContainText('Sales')
    await expect(page.getByRole('row', { name: 'Leo Logistics' })).toContainText('Logistics')
    await expect(page.getByRole('row', { name: 'Quinn Quality' })).toContainText('Quality')
    await page.getByRole('row', { name: 'Leo Logistics' }).getByRole('button', { name: 'Edit' }).click()
    const ce = page.getByRole('dialog', { name: 'Edit contact' })
    await ce.getByLabel('Contact role').selectOption('quality')
    await ce.getByRole('button', { name: 'Save contact' }).click()
    await expect(page.getByRole('row', { name: 'Leo Logistics' })).toContainText('Quality')
    await expect(page.getByRole('table', { name: 'Vendor codes' })).toHaveCount(0) // customers only

    // Remove → reactivate.
    await page.getByRole('button', { name: 'Remove vendor' }).click()
    await confirmIn(page, 'Remove vendor')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Removed')
    await openPartner(page, 'vendor', v.code, 'false')
    await page.getByRole('button', { name: 'Reactivate' }).click()
    await expect(page.getByRole('status')).toHaveText(`${v.legal} reactivated.`)
  })

  test('a viewer reads vendors; an editor edits but cannot delete permanently', async ({ page, browser }) => {
    await signInExpectingSuccess(page, ADMIN)
    const viewer = uniqueEmail('vendor.viewer')
    const editor = uniqueEmail('vendor.editor')
    await addUser(page, viewer, 'viewer')
    await addUser(page, editor, 'editor')
    const id = uid()
    const v = { code: `RO-${id}`, legal: `Read Only Vendor ${id}`, country: 'CN', currency: 'USD' }
    await addPartner(page, 'vendor', v)
    await addAddress(page, 'factory', 'Ningbo')

    const vctx = await browser.newContext()
    const vp = await vctx.newPage()
    await signInExpectingSuccess(vp, viewer)
    await openPartner(vp, 'vendor', v.code)
    await expect(rowsOf(vp, 'Addresses')).toHaveCount(1)
    for (const name of ['Edit vendor', 'Remove vendor', 'Add address', 'Add contact']) {
      await expect(vp.getByRole('button', { name })).toHaveCount(0)
    }
    await vp.goto('/vendors')
    await expect(vp.getByRole('button', { name: 'Add vendor' })).toHaveCount(0)
    await vctx.close()

    const ectx = await browser.newContext()
    const ep = await ectx.newPage()
    await signInExpectingSuccess(ep, editor)
    await openPartner(ep, 'vendor', v.code)
    await ep.getByRole('button', { name: 'Remove vendor' }).click()
    await confirmIn(ep, 'Remove vendor')
    await expect(ep.getByRole('button', { name: 'Reactivate' })).toBeVisible()
    await expect(ep.getByRole('button', { name: 'Delete permanently' })).toHaveCount(0)
    await ectx.close()
  })
})
