import { expect, test, type Page } from '@playwright/test'
import { ADMIN, addUser, signInAs, signInExpectingSuccess, uniqueEmail } from './helpers'

async function openUser(page: Page, email: string): Promise<void> {
  await page.getByRole('searchbox', { name: 'Search users' }).fill(email)
  await page.getByRole('row', { name: email }).click()
  await expect(page.getByRole('dialog', { name: 'User details' })).toBeVisible()
}

test.describe('Users (admin)', () => {
  test.beforeEach(async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
  })

  test('list, search, filter and sort', async ({ page }) => {
    const a = uniqueEmail('aaa.list')
    const z = uniqueEmail('zzz.list')
    await addUser(page, a, 'viewer')
    await addUser(page, z, 'editor')

    const rows = page.locator('table.data-table tbody tr')
    await expect(page.getByRole('row', { name: ADMIN })).toBeVisible()

    await page.getByRole('searchbox', { name: 'Search users' }).fill('.list.')
    await expect(rows).toHaveCount(2)

    // Sort by email, descending: zzz first.
    await page.getByRole('button', { name: 'Email' }).click() // already asc → desc
    await expect(rows.first()).toContainText('zzz.list')
    await page.getByRole('button', { name: 'Email' }).click()
    await expect(rows.first()).toContainText('aaa.list')

    await page.getByRole('combobox', { name: 'Filter by role' }).selectOption('editor')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText(z)
  })

  test('add, view, edit and remove a user — then they cannot sign in', async ({ page, browser }) => {
    const email = uniqueEmail('lifecycle')

    // Add
    await addUser(page, email, 'viewer')

    // Validation: wrong domain is refused in the form.
    await page.getByRole('button', { name: 'Add user' }).click()
    const add = page.getByRole('dialog', { name: 'Add user' })
    await add.getByLabel('Email').fill('outsider@gmail.com')
    await add.getByRole('button', { name: 'Add user' }).click()
    await expect(add.getByText('Must be an @buenavidatrading.com address')).toBeVisible()
    await add.getByRole('button', { name: 'Close' }).click()

    // View + edit
    await openUser(page, email)
    const details = page.getByRole('dialog', { name: 'User details' })
    await expect(details.getByText(email)).toBeVisible()
    await expect(details.getByText('Never')).toBeVisible() // last sign-in
    await details.getByLabel('Display name').fill('Lifecycle Person')
    await details.getByLabel('Role').selectOption('editor')
    await details.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toContainText(`${email} saved`)
    const row = page.getByRole('row', { name: email })
    await expect(row).toContainText('Lifecycle Person')
    await expect(row).toContainText('editor')

    // The user can sign in now (separate browser).
    const ctx = await browser.newContext()
    const userPage = await ctx.newPage()
    await signInExpectingSuccess(userPage, email)
    await expect(userPage.locator('.badge')).toHaveText('editor')

    // Remove (soft delete) with confirmation.
    await openUser(page, email)
    await details.getByRole('button', { name: 'Remove user' }).click()
    const confirm = page.getByRole('dialog', { name: 'Remove user' })
    await expect(confirm).toContainText('will no longer be able to sign in')
    await confirm.getByRole('button', { name: 'Remove' }).click()
    await expect(page.getByRole('status')).toContainText(`${email} saved`)
    await expect(page.getByRole('row', { name: email })).toHaveCount(0) // list shows active users

    // Their open session ended immediately...
    await userPage.reload()
    await expect(userPage.getByRole('link', { name: 'Sign in with Google' })).toBeVisible()
    // ...and they can't sign in again.
    await signInAs(userPage, email)
    await expect(userPage).toHaveURL(/\/no-access\?reason=not_allowed/)
    await ctx.close()

    // Still in the database: visible under "Removed", and can be reactivated.
    await page.getByRole('combobox', { name: 'Filter by status' }).selectOption('false')
    await openUser(page, email)
    await expect(details.getByText('Removed (cannot sign in)')).toBeVisible()
    await details.getByRole('button', { name: 'Reactivate' }).click()
    await expect(page.getByRole('status')).toContainText(`${email} saved`)
    await page.getByRole('combobox', { name: 'Filter by status' }).selectOption('true')
    await expect(page.getByRole('row', { name: email })).toBeVisible()
  })

  test('an admin cannot remove their own access', async ({ page }) => {
    await page.getByRole('link', { name: 'Users' }).click()
    await openUser(page, ADMIN)
    const details = page.getByRole('dialog', { name: 'User details' })
    await expect(details.getByLabel('Role')).toBeDisabled()
    await expect(details.getByRole('button', { name: 'Remove user' })).toBeDisabled()
  })

  test('two admins editing the same user: the second save gets "someone else changed this"', async ({
    page,
    browser,
  }) => {
    const email = uniqueEmail('conflict')
    await addUser(page, email, 'viewer')
    await openUser(page, email) // tab 1 holds version 1

    const ctx = await browser.newContext()
    const other = await ctx.newPage()
    await signInExpectingSuccess(other, ADMIN)
    await other.getByRole('link', { name: 'Users' }).click()
    await openUser(other, email)
    const otherDetails = other.getByRole('dialog', { name: 'User details' })
    await otherDetails.getByLabel('Role').selectOption('editor')
    await otherDetails.getByRole('button', { name: 'Save changes' }).click()
    await expect(other.getByRole('status')).toContainText('saved')
    await ctx.close()

    const details = page.getByRole('dialog', { name: 'User details' })
    await details.getByLabel('Display name').fill('Stale edit')
    await details.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('status')).toContainText('Someone else changed this record')
    await expect(page.getByRole('row', { name: email })).toContainText('editor')
    await expect(page.getByRole('row', { name: email })).not.toContainText('Stale edit')
  })
})

test('every column the API can sort is sortable in the Users table', async ({ page }) => {
  await signInExpectingSuccess(page, ADMIN)
  await page.getByRole('link', { name: 'Users' }).click()
  for (const name of ['Email', 'Name', 'Role', 'Last sign-in']) {
    await expect(page.getByRole('columnheader', { name }).getByRole('button')).toBeVisible()
  }
})
