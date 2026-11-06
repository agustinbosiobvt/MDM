// Spec corrections of 2026-10-16: no Tax ID anywhere, no currency on Company,
// no separate "Price lists" menu (price lists will live inside customers/vendors).
import { expect, test } from '@playwright/test'
import { ADMIN, signInExpectingSuccess } from './helpers'

test.describe('Spec corrections', () => {
  test.beforeEach(async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
  })

  test('there is no separate Price lists menu or page', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'Main' })
    await expect(nav.getByRole('link')).toHaveText(['Home', 'Company', 'Customers', 'Vendors', 'Users'])
    await expect(nav.getByRole('link', { name: /price/i })).toHaveCount(0)
    await page.goto('/price-lists')
    await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible()
  })

  test('Company: no Tax ID and no currency, in the list, the form and the API', async ({ page }) => {
    await page.goto('/company')
    await expect(page.getByRole('searchbox', { name: 'Search companies' })).toHaveAttribute('placeholder', 'Search code or name')
    const headers = page.getByRole('columnheader')
    await expect(headers).not.toContainText(['Tax ID'])
    await expect(headers.filter({ hasText: /Tax ID|Currency/ })).toHaveCount(0)

    await page.getByRole('button', { name: 'Add company' }).click()
    const d = page.getByRole('dialog', { name: 'Add company' })
    await expect(d.getByLabel('Legal name')).toBeVisible()
    await expect(d.getByText(/Tax ID|VAT/)).toHaveCount(0)
    await expect(d.getByLabel('Tax registration number')).toBeVisible() // Company only
    await expect(d.getByText(/currency/i)).toHaveCount(0)

    const csrf = (await page.context().cookies()).find((c) => c.name === '__Host-mdm_csrf')?.value ?? ''
    const r = await page.request.post('/api/companies', {
      headers: { 'X-CSRF-Token': csrf, Origin: 'http://localhost:8080' },
      data: { code: 'NOPE1', legal_name: 'x', country_code: 'ES', tax_id: 'B1', base_currency: 'EUR' },
    })
    expect(r.status()).toBe(422)
  })

  for (const [path, noun, search] of [
    ['/customers', 'customer', 'Search customers'],
    ['/vendors', 'vendor', 'Search vendors'],
  ] as const) {
    test(`${noun}s: no Tax ID, but the default currency stays`, async ({ page }) => {
      await page.goto(path)
      await expect(page.getByRole('searchbox', { name: search })).toHaveAttribute('placeholder', 'Search code or name')
      await expect(page.getByRole('columnheader').filter({ hasText: 'Tax ID' })).toHaveCount(0)
      await expect(page.getByRole('columnheader', { name: 'Currency' })).toBeVisible()
      await page.getByRole('button', { name: `Add ${noun}` }).click()
      const d = page.getByRole('dialog', { name: `Add ${noun}` })
      await expect(d.getByText('Tax ID')).toHaveCount(0)
      await expect(d.getByText('Tax registration number')).toHaveCount(0) // Company only
      await expect(d.getByLabel('Default currency')).toBeVisible()
    })
  }
})
