import { expect, type Page } from '@playwright/test'

export const ADMIN = 'e2e-admin@buenavidatrading.com' // BOOTSTRAP_ADMIN_EMAIL in docker-compose.e2e.yml
export const DOMAIN = 'buenavidatrading.com'

/** A unique address per test run, so reruns never collide. */
export function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString()}@${DOMAIN}`
}

interface SignInOptions {
  emailVerified?: boolean
  hd?: string
}

/** Click "Sign in with Google", pick the account on the (mock) Google screen, come back. */
export async function signInAs(page: Page, email: string, opts: SignInOptions = {}): Promise<void> {
  await page.goto('/')
  await page.getByRole('link', { name: 'Sign in with Google' }).click()
  await expect(page).toHaveURL(/localhost:8090\/authorize/)
  await page.getByLabel('Google account email').fill(email)
  if (opts.emailVerified === false) await page.getByLabel('Email verified').uncheck()
  if (opts.hd !== undefined) await page.getByLabel('Hosted domain (hd)').fill(opts.hd)
  await page.getByRole('button', { name: 'Continue' }).click()
}

export async function signInExpectingSuccess(page: Page, email: string): Promise<void> {
  await signInAs(page, email)
  await expect(page.getByRole('heading', { name: /^Welcome/ })).toBeVisible()
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('link', { name: 'Sign in with Google' })).toBeVisible()
}

/** Collects console errors (CSP violations show up here). */
export function watchConsole(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

/** Add a user through the Users screen (as an admin). */
export async function addUser(page: Page, email: string, role: 'viewer' | 'editor' | 'admin'): Promise<void> {
  await page.getByRole('link', { name: 'Users' }).click()
  await page.getByRole('button', { name: 'Add user' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add user' })
  await dialog.getByLabel('Email').fill(email)
  await dialog.getByLabel('Role').selectOption(role)
  await dialog.getByRole('button', { name: 'Add user' }).click()
  await expect(page.getByRole('status')).toContainText(`${email} added as ${role}`)
}
