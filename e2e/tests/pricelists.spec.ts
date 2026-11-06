import fs from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { ADMIN, addUser, signInExpectingSuccess, uniqueEmail } from './helpers'
import { addPartner, uid } from './partner-helpers'

const SAMPLES = path.resolve(import.meta.dirname, '../../samples')
const AMAZON = path.join(SAMPLES, 'Client prices AmzMx.xlsx')
const NOBBY = path.join(SAMPLES, 'NOBBY_PLS_GEN_Pl-0-2025-Englisch-With-Details_2026-09-12_v01.xlsx')
const DUPES = path.resolve(import.meta.dirname, '../fixtures/duplicates.csv')
const haveSamples = fs.existsSync(AMAZON) && fs.existsSync(NOBBY)

// Performance targets (CLAUDE.md §6), per sample file in this Docker stack.
const TARGET = { preview: 5_000, validate: 15_000, commit: 30_000, lines: 1_000 }

const priceSection = (page: Page) => page.getByRole('region', { name: 'Price list' })
const report = (page: Page) => page.getByLabel('Validation summary')
const stat = (page: Page, label: string) => report(page).locator('.stat').filter({ hasText: label }).locator('.stat-value')

async function startImport(page: Page, file: string): Promise<number> {
  await priceSection(page).getByRole('button', { name: 'Import price list' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Import price list' })).toBeVisible()
  await page.getByLabel('Price list file').setInputFiles(file)
  const t0 = Date.now()
  await page.getByRole('button', { name: 'Upload' }).click()
  return t0
}

async function confirmAndValidate(page: Page): Promise<number> {
  await page.getByLabel('I have checked the price types and currencies above.').check()
  const t0 = Date.now()
  await page.getByRole('button', { name: 'Validate' }).click()
  await expect(report(page)).toBeVisible({ timeout: 60_000 })
  return Date.now() - t0
}

async function importIt(page: Page, details: { name: string; currency: string; validFrom?: string; template?: string | null }) {
  await page.getByLabel('Name', { exact: true }).fill(details.name)
  await page.getByLabel('List currency').selectOption(details.currency)
  if (details.validFrom) await page.getByLabel('Valid from').fill(details.validFrom)
  const tpl = page.getByLabel('Save this mapping as a template for next time')
  if (details.template === null) {
    if (await tpl.isChecked()) await tpl.uncheck()
  } else if (details.template) {
    await tpl.check()
    await page.getByLabel('Template name').fill(details.template)
  }
  const t0 = Date.now()
  await page.getByRole('button', { name: /^Import [\d,]+ lines$/ }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Identity and terms' })).toBeVisible({ timeout: 60_000 })
  return Date.now() - t0
}

test.describe('Price lists inside customers and vendors', () => {
  test.beforeEach(async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
  })

  test('Amazon MX file: wizard, report counts, filters, edit category, activate, one-click re-import', async ({ page }) => {
    test.skip(!haveSamples, 'sample files not present in ./samples')
    test.setTimeout(180_000)
    const id = uid()
    await addPartner(page, 'customer', { code: `AMZ-${id}`, legal: `Amazon MX ${id}`, country: 'MX', currency: 'MXN' })
    await expect(priceSection(page)).toContainText('No price list yet')

    // 1-2. Upload → sheet and header detected.
    const t0 = await startImport(page, AMAZON)
    await expect(page.getByLabel('Header row')).toHaveValue('4')
    const previewMs = Date.now() - t0
    await expect(page.getByLabel('Data starts at row')).toHaveValue('7')
    await expect(page.getByLabel('Sheet')).toHaveValue('ALL')
    await expect(page.getByRole('table', { name: 'File preview' })).toContainText('B003QQ37HI')
    await page.getByRole('button', { name: 'Next: map columns' }).click()

    // 3. Suggested mapping: brand from "Brand Name", no category column, RRP currency from column W.
    await expect(page.getByRole('combobox', { name: 'Brand', exact: true })).toHaveValue('10') // column K
    await expect(page.getByRole('combobox', { name: 'Category', exact: true })).toHaveValue('')
    await expect(page.getByRole('combobox', { name: 'Price 3 currency source' })).toHaveValue('column')
    await expect(page.getByRole('combobox', { name: 'Price 3 currency column' })).toHaveValue('22') // W
    await expect(page.getByRole('button', { name: 'Validate' })).toBeDisabled() // until confirmed
    const validateMs = await confirmAndValidate(page)

    // 4. Report.
    await expect(stat(page, 'Rows read')).toHaveText('7,515')
    await expect(stat(page, 'Lines OK')).toHaveText('7,514')
    await expect(stat(page, 'Lines with warnings')).toHaveText('1')
    await expect(stat(page, 'Rows rejected')).toHaveText('0')
    await expect(stat(page, 'Prices')).toHaveText('15,030')
    const found = page.getByRole('table', { name: 'Prices found' })
    await expect(found.getByRole('row', { name: /Import cost USD 7,515/ })).toBeVisible()
    await expect(found.getByRole('row', { name: /RRP MXN 7,515/ })).toBeVisible()
    await expect(page.getByRole('table', { name: 'Issues' })).toContainText("'43917996264' is not a valid GTIN")
    const commitMs = await importIt(page, { name: `Amazon MX ${id}`, currency: 'MXN', validFrom: '2026-10-01', template: 'Amazon quote sheet' })
    await expect(page.getByRole('status').first()).toContainText('Imported revision 1 as a draft: 7,515 lines, 15,030 prices.')

    // Price list section: status, last update + who, lines, filters.
    const s = priceSection(page)
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Draft')
    await expect(s.getByLabel('Last update')).toContainText(`by ${ADMIN}`)
    await expect(s.getByLabel('Price list details')).toContainText('7,515')
    await expect(s.getByRole('combobox', { name: 'Filter by brand' })).toContainText('Nobby (7,515)')
    await expect(s.getByRole('combobox', { name: 'Filter by category' })).toContainText('None (7,515)')
    await expect(s.getByRole('columnheader', { name: 'Import cost USD' })).toBeVisible()
    await expect(s.getByRole('columnheader', { name: 'RRP MXN' })).toBeVisible()

    let t = Date.now()
    await s.getByRole('searchbox', { name: 'Search lines' }).fill('4033766024146')
    await expect(s.getByRole('table', { name: 'Price list lines' }).locator('tbody tr')).toHaveCount(1)
    const filterMs = Date.now() - t
    await expect(s.getByRole('row', { name: 'Row 8' })).toContainText('180.6273') // exact, no float rounding
    await s.getByRole('searchbox', { name: 'Search lines' }).fill('B003QQ37HI') // ASIN
    await expect(s.getByRole('table', { name: 'Price list lines' }).locator('tbody tr')).toHaveCount(1)

    // Edit the category of one line (prices are not editable).
    await s.getByRole('row', { name: 'Row 7' }).click()
    const d = page.getByRole('dialog', { name: 'Product details' })
    await expect(d).toContainText('Import cost: 78.1126 USD')
    await expect(d).toContainText('RRP: 3,728.82 MXN')
    await d.getByLabel('Category').fill('Bags')
    await d.getByRole('button', { name: 'Save' }).click()
    await expect(s.getByRole('status')).toHaveText('Line saved.')
    await s.getByRole('searchbox', { name: 'Search lines' }).fill('')
    await s.getByRole('combobox', { name: 'Filter by category' }).selectOption('Bags')
    await expect(s.getByRole('table', { name: 'Price list lines' }).locator('tbody tr')).toHaveCount(1)
    t = Date.now()
    await s.getByRole('combobox', { name: 'Filter by category' }).selectOption('')
    await s.getByRole('combobox', { name: 'Filter by brand' }).selectOption('Nobby')
    await expect(s.locator('.pager')).toContainText('7,515 records')
    const brandMs = Date.now() - t

    // Activate.
    await s.getByRole('button', { name: 'Activate' }).click()
    await page.getByRole('dialog', { name: 'Activate price list' }).getByRole('button', { name: 'Activate' }).click()
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Active')

    // Next month: one click with the saved template → new version; the old one expires on activation.
    await startImport(page, AMAZON)
    await expect(page.getByText('This exact file was already imported (revision 1)')).toBeVisible()
    await page.getByRole('button', { name: 'Use “Amazon quote sheet”' }).click()
    await expect(stat(page, 'Rows read')).toHaveText('7,515')
    await importIt(page, { name: `Amazon MX ${id} v2`, currency: 'MXN', validFrom: '2026-11-01', template: null })
    await expect(page.getByRole('status').first()).toContainText('Imported revision 2 as a draft')
    const history = s.getByRole('table', { name: 'Version history' })
    await expect(history.getByRole('row', { name: 'Revision 2' })).toContainText('Draft')
    await expect(history.getByRole('row', { name: 'Revision 1' })).toContainText('Active')
    await s.getByRole('button', { name: 'Activate' }).click()
    await page.getByRole('dialog', { name: 'Activate price list' }).getByRole('button', { name: 'Activate' }).click()
    await expect(history.getByRole('row', { name: 'Revision 1' })).toContainText('Expired')
    await expect(history.getByRole('row', { name: 'Revision 2' })).toContainText('Active')
    await history.getByRole('row', { name: 'Revision 1' }).click()
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Rev 1') // history stays viewable
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Expired')

    console.log(`Amazon timings: preview ${previewMs} ms, validate ${validateMs} ms, commit ${commitMs} ms, search ${filterMs} ms, brand filter ${brandMs} ms`)
    expect(previewMs).toBeLessThan(TARGET.preview)
    expect(validateMs).toBeLessThan(TARGET.validate)
    expect(commitMs).toBeLessThan(TARGET.commit)
    expect(filterMs).toBeLessThan(TARGET.lines + 500) // + debounce of the search box
    expect(brandMs).toBeLessThan(TARGET.lines)
  })

  test('Nobby file: duplicate headers, currencies from € / (MXN) / (USD) headers, every price with its currency', async ({ page }) => {
    test.skip(!haveSamples, 'sample files not present in ./samples')
    test.setTimeout(180_000)
    const id = uid()
    await addPartner(page, 'vendor', { code: `NOB-${id}`, legal: `Nobby Pet Shop ${id} GmbH`, country: 'DE', currency: 'EUR' })
    const t0 = await startImport(page, NOBBY)
    await expect(page.getByLabel('Header row')).toHaveValue('7')
    const previewMs = Date.now() - t0
    await expect(page.getByLabel('Data starts at row')).toHaveValue('8')
    await expect(page.getByText('valid from 15.08.2025')).toBeVisible() // metadata above the header
    await page.getByRole('button', { name: 'Next: map columns' }).click()
    await expect(page.getByRole('combobox', { name: 'ASIN', exact: true })).toHaveValue('2') // first of four ASIN columns
    // Currencies suggested from the headers ("PRICE €", "MX RRP (MXN)"...); margins are not prices.
    await expect(page.getByRole('combobox', { name: 'Price 1 currency', exact: true })).toHaveValue('EUR')
    await expect(page.getByRole('combobox', { name: 'Price 2 currency', exact: true })).toHaveValue('EUR')
    await expect(page.getByRole('combobox', { name: 'Price 6 currency', exact: true })).toHaveValue('USD')
    // Six prices; the margin columns (O, P, Y) are not among them.
    await expect(page.getByRole('table', { name: 'Price columns' }).locator('tbody tr')).toHaveCount(6)
    await expect(page.getByRole('combobox', { name: 'Price 1 column' })).toHaveValue('11') // L
    await expect(page.getByRole('combobox', { name: 'Price 6 column' })).toHaveValue('23') // X
    const validateMs = await confirmAndValidate(page)
    await expect(stat(page, 'Lines OK')).toHaveText('7,514')
    await expect(stat(page, 'Prices')).toHaveText('45,061')
    const found = page.getByRole('table', { name: 'Prices found' })
    for (const [type, ccy, n] of [
      ['Purchase price', 'EUR', '7,486'],
      ['RRP', 'EUR', '7,515'],
      ['RRP', 'MXN', '7,515'],
      ['RRP ex VAT', 'MXN', '7,515'],
      ['Retailer cost', 'MXN', '7,515'],
      ['Retailer cost', 'USD', '7,515'],
    ]) {
      await expect(found.getByRole('row', { name: `${type} ${ccy} ${n}` })).toBeVisible()
    }
    await expect(page.getByLabel('Valid from')).toHaveValue('2025-08-15') // suggested from the file
    const commitMs = await importIt(page, { name: `Nobby ${id}`, currency: 'EUR', template: 'Nobby export list' })
    console.log(`Nobby timings: preview ${previewMs} ms, validate ${validateMs} ms, commit ${commitMs} ms`)
    expect(previewMs).toBeLessThan(TARGET.preview)
    expect(validateMs).toBeLessThan(TARGET.validate)
    expect(commitMs).toBeLessThan(TARGET.commit)
    await expect(page.getByRole('status').first()).toContainText('7,515 lines, 45,061 prices')
    const s = priceSection(page)
    await s.getByRole('row', { name: 'Row 8' }).click()
    const d = page.getByRole('dialog', { name: 'Product details' })
    for (const text of [
      'Purchase price: 50.00 EUR',
      'RRP: 125.00 EUR',
      'RRP: 3,728.82 MXN',
      'RRP ex VAT: 3,214.50 MXN',
      'Retailer cost: 1,446.53 MXN',
      'Retailer cost: 78.1126 USD',
    ]) {
      await expect(d).toContainText(text)
    }
    await expect(d).toContainText('DE / 39232100') // origin / HS code
  })

  test('D4: duplicates are imported and flagged; activation waits until they are resolved', async ({ page }) => {
    const id = uid()
    await addPartner(page, 'customer', { code: `DUP-${id}`, legal: `Duplicates ${id}`, country: 'MX', currency: 'MXN' })
    await startImport(page, DUPES)
    await expect(page.getByLabel('Sheet')).toHaveValue('CSV')
    await page.getByRole('button', { name: 'Next: map columns' }).click()
    const chips = page.locator('.chip')
    await expect(chips).toHaveCount(2) // destination country + shipping port suggested
    await confirmAndValidate(page)
    await expect(stat(page, 'Duplicate groups')).toHaveText('1')
    await expect(stat(page, 'Rows read')).toHaveText('5')
    await importIt(page, { name: `Dupes ${id}`, currency: 'USD', template: null })
    const s = priceSection(page)
    await expect(s.getByRole('alert')).toContainText('1 duplicate group(s).')
    await s.getByRole('button', { name: 'Activate' }).click()
    await page.getByRole('dialog', { name: 'Activate price list' }).getByRole('button', { name: 'Activate' }).click()
    await expect(s.getByRole('alert').filter({ hasText: 'Exclude the extra lines' })).toBeVisible()
    await s.getByRole('button', { name: 'Show duplicates' }).click()
    await expect(s.getByRole('table', { name: 'Price list lines' }).locator('tbody tr')).toHaveCount(2)
    await s.getByRole('row', { name: 'Row 4' }).click()
    await page.getByRole('dialog', { name: 'Product details' }).getByRole('button', { name: 'Exclude line' }).click()
    await expect(s.getByRole('status')).toHaveText('Line excluded.')
    await expect(s.getByText('duplicate group(s).')).toHaveCount(0)
    await s.getByRole('button', { name: 'Activate' }).click()
    await page.getByRole('dialog', { name: 'Activate price list' }).getByRole('button', { name: 'Activate' }).click()
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Active')
    await expect(s.getByRole('button', { name: 'Delete draft' })).toHaveCount(0) // only drafts
  })

  test('a draft can be deleted after confirming; the active version stays', async ({ page }) => {
    const id = uid()
    await addPartner(page, 'vendor', { code: `DEL-${id}`, legal: `Draft delete ${id}`, country: 'DE', currency: 'EUR' })
    await startImport(page, DUPES)
    await page.getByRole('button', { name: 'Next: map columns' }).click()
    await confirmAndValidate(page)
    await importIt(page, { name: `Keep ${id}`, currency: 'USD', template: null })
    const s = priceSection(page)
    await s.getByRole('button', { name: 'Show duplicates' }).click()
    await s.getByRole('row', { name: 'Row 4' }).click()
    await page.getByRole('dialog', { name: 'Product details' }).getByRole('button', { name: 'Exclude line' }).click()
    await expect(s.getByRole('status')).toHaveText('Line excluded.')
    await s.getByRole('button', { name: 'Activate' }).click()
    await page.getByRole('dialog', { name: 'Activate price list' }).getByRole('button', { name: 'Activate' }).click()
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Active')

    await startImport(page, DUPES)
    await page.getByRole('button', { name: 'Next: map columns' }).click()
    await confirmAndValidate(page)
    await importIt(page, { name: `Mistake ${id}`, currency: 'USD', template: null })
    await expect(s.getByRole('heading', { level: 3 })).toContainText(`Mistake ${id}`)
    // Cancel keeps it.
    await s.getByRole('button', { name: 'Delete draft' }).click()
    const dlg = page.getByRole('dialog', { name: 'Delete draft' })
    await expect(dlg).toContainText(`Mistake ${id}`)
    await dlg.getByRole('button', { name: 'Cancel' }).click()
    await expect(s.getByRole('table', { name: 'Version history' }).getByRole('row', { name: 'Revision 2' })).toBeVisible()
    // Confirm deletes it; the active Rev 1 is shown again.
    await s.getByRole('button', { name: 'Delete draft' }).click()
    await dlg.getByRole('button', { name: 'Delete draft' }).click()
    await expect(s.getByRole('heading', { level: 3 })).toContainText(`Keep ${id}`)
    await expect(s.getByRole('heading', { level: 3 })).toContainText('Active')
    await expect(s.getByText(`Mistake ${id}`)).toHaveCount(0)
    await expect(s.getByRole('button', { name: 'Delete draft' })).toHaveCount(0)
  })

  test('uploads are checked: wrong type and fake .xlsx are refused', async ({ page }) => {
    const id = uid()
    await addPartner(page, 'vendor', { code: `UPL-${id}`, legal: `Upload checks ${id}`, country: 'DE' })
    await priceSection(page).getByRole('button', { name: 'Import price list' }).click()
    const input = page.getByLabel('Price list file')
    await input.setInputFiles({ name: 'prices.xlsm', mimeType: 'application/vnd.ms-excel.sheet.macroEnabled.12', buffer: Buffer.from('x') })
    await expect(page.getByText('Only .xlsx and .csv files can be imported.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Upload' })).toBeDisabled()
    await input.setInputFiles({ name: 'prices.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('not really a workbook') })
    await page.getByRole('button', { name: 'Upload' }).click()
    await expect(page.getByRole('alert')).toHaveText('This is not a valid .xlsx file.')
    await page.getByRole('button', { name: 'Cancel import' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Identity and terms' })).toBeVisible()
  })

  test('a viewer sees the price list but cannot import, edit or activate', async ({ page, browser }) => {
    const id = uid()
    const viewer = uniqueEmail('pl.viewer')
    await addUser(page, viewer, 'viewer')
    await addPartner(page, 'customer', { code: `VW-${id}`, legal: `Viewer check ${id}`, country: 'MX', currency: 'MXN' })
    await startImport(page, DUPES)
    await page.getByRole('button', { name: 'Next: map columns' }).click()
    await confirmAndValidate(page)
    await importIt(page, { name: `Viewer list ${id}`, currency: 'USD', template: null })
    const url = page.url()

    const ctx = await browser.newContext()
    const v = await ctx.newPage()
    await signInExpectingSuccess(v, viewer)
    await v.goto(url)
    const s = priceSection(v)
    await expect(s.getByRole('heading', { level: 3 })).toContainText(`Viewer list ${id}`)
    await expect(s.getByRole('button', { name: 'Import price list' })).toHaveCount(0)
    await expect(s.getByRole('button', { name: 'Activate' })).toHaveCount(0)
    await expect(s.getByRole('button', { name: 'Delete draft' })).toHaveCount(0)
    await s.getByRole('row', { name: 'Row 2' }).click()
    const d = v.getByRole('dialog', { name: 'Product details' })
    await expect(d.getByRole('button', { name: 'Save' })).toHaveCount(0)
    await expect(d.getByLabel('Category')).toHaveCount(0)
    await v.goto(`${url}/import`)
    await expect(v.getByRole('heading', { name: 'Not allowed' })).toBeVisible()
    await ctx.close()
  })
})
