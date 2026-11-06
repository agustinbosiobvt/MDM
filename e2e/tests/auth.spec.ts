import { expect, test } from '@playwright/test'
import { ADMIN, addUser, signInAs, signInExpectingSuccess, signOut, uniqueEmail, watchConsole } from './helpers'

test.describe('Google sign-in', () => {
  test('anonymous visitors see only the sign-in page', async ({ page }) => {
    await page.goto('/users')
    await expect(page.getByRole('link', { name: 'Sign in with Google' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
    const api = await page.request.get('/api/me')
    expect(api.status()).toBe(401)
  })

  test('the bootstrap admin signs in and out', async ({ page, context }) => {
    const consoleErrors = watchConsole(page)
    await signInExpectingSuccess(page, ADMIN)
    await expect(page.locator('.badge')).toHaveText('admin')
    await expect(page.getByRole('link', { name: 'Users' })).toBeVisible()
    await expect(page.getByText('Database')).toBeVisible()

    // Session cookie: opaque, HttpOnly, Secure, SameSite=Lax, host-only.
    const cookies = await context.cookies()
    const session = cookies.find((c) => c.name === '__Host-mdm_session')
    expect(session).toBeDefined()
    expect(session?.httpOnly).toBe(true)
    expect(session?.secure).toBe(true)
    expect(session?.sameSite).toBe('Lax')
    expect(session?.path).toBe('/')
    expect(session?.value).not.toMatch(/^eyJ/) // not a JWT

    // Nothing sensitive is reachable from page JavaScript or stored in the browser.
    const js = await page.evaluate(() => ({
      cookie: document.cookie,
      local: Object.keys(localStorage).length,
      sessionStore: Object.keys(sessionStorage).length,
    }))
    expect(js.cookie).not.toContain('mdm_session')
    expect(js.local).toBe(0)
    expect(js.sessionStore).toBe(0)

    const oldSession = session?.value ?? ''
    await signOut(page)
    await page.reload()
    await expect(page.getByRole('link', { name: 'Sign in with Google' })).toBeVisible()

    // The old session is dead on the server, not just forgotten by the browser.
    const replay = await page.request.get('/api/me', {
      headers: { cookie: `__Host-mdm_session=${oldSession}` },
    })
    expect(replay.status()).toBe(401)

    expect(consoleErrors.filter((e) => /Content Security Policy|Refused to/i.test(e))).toEqual([])
  })

  test('pages are served with security headers', async ({ page }) => {
    const res = await page.goto('/')
    const h = res?.headers() ?? {}
    expect(h['content-security-policy']).toContain("script-src 'self'")
    expect(h['content-security-policy']).toContain("frame-ancestors 'none'")
    expect(h['x-frame-options']).toBe('DENY')
    expect(h['x-content-type-options']).toBe('nosniff')
    expect(h['referrer-policy']).toBe('no-referrer')
  })

  test('an account that is not on the allow-list gets "No access"', async ({ page }) => {
    await signInAs(page, uniqueEmail('stranger'))
    await expect(page).toHaveURL(/\/no-access\?reason=not_allowed/)
    await expect(page.getByRole('heading', { name: 'No access' })).toBeVisible()
    await expect(page.getByRole('alert')).toContainText("isn't allowed")
    expect((await page.request.get('/api/me')).status()).toBe(401)
  })

  test('a consumer Google account (no hosted domain) is refused', async ({ page }) => {
    await signInAs(page, 'someone@gmail.com')
    await expect(page).toHaveURL(/\/no-access\?reason=not_allowed/)
  })

  test('an allow-listed email with an unverified address is refused', async ({ page }) => {
    await signInAs(page, ADMIN, { emailVerified: false })
    await expect(page).toHaveURL(/\/no-access\?reason=not_allowed/)
  })

  test('cancelling at Google shows a clear message', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'Sign in with Google' }).click()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page).toHaveURL(/\/no-access\?reason=cancelled/)
    await expect(page.getByRole('alert')).toHaveText('Sign-in was cancelled.')
  })

  test('a viewer sees no admin screens and the API refuses admin calls', async ({ browser }) => {
    const viewer = uniqueEmail('viewer')
    const adminCtx = await browser.newContext()
    const admin = await adminCtx.newPage()
    await signInExpectingSuccess(admin, ADMIN)
    await addUser(admin, viewer, 'viewer')
    await adminCtx.close()

    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await signInExpectingSuccess(page, viewer)
    await expect(page.locator('.badge')).toHaveText('viewer')
    await expect(page.getByRole('link', { name: 'Users' })).toHaveCount(0)

    await page.goto('/users')
    await expect(page.getByRole('heading', { name: 'Not allowed' })).toBeVisible()

    // Hiding the link is not the security: the server refuses too.
    expect((await page.request.get('/api/users')).status()).toBe(403)
    const csrf = (await ctx.cookies()).find((c) => c.name === '__Host-mdm_csrf')?.value ?? ''
    const post = await page.request.post('/api/users', {
      headers: { 'X-CSRF-Token': csrf, Origin: 'http://localhost:8080' },
      data: { email: uniqueEmail('sneaky'), role: 'admin' },
    })
    expect(post.status()).toBe(403)
    await ctx.close()
  })

  test('state-changing calls without the CSRF token are refused', async ({ page }) => {
    await signInExpectingSuccess(page, ADMIN)
    const noToken = await page.request.post('/auth/logout', {
      headers: { Origin: 'http://localhost:8080' },
    })
    expect(noToken.status()).toBe(403)
    const crossSite = await page.request.post('/auth/logout', {
      headers: { Origin: 'https://evil.example' },
    })
    expect(crossSite.status()).toBe(403)
    // Still signed in.
    await page.reload()
    await expect(page.getByRole('heading', { name: /^Welcome/ })).toBeVisible()
  })
})
