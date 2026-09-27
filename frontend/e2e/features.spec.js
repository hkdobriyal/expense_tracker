import fs from 'node:fs'
import { expect, test } from '@playwright/test'

// Runs after core-flow.spec.js. Registers its own user so it is independent.
const PASSWORD = 'FeatureTest9'
const CSV = [
  'HDFC BANK Ltd. Statement of account',
  'Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance',
  '01/09/26,NEFT CR-ICIC0000104-ACME TECHNOLOGIES-SALARY SEP,N1,01/09/26,,"85,000.00","85,000.00"',
  '03/09/26,UPI/DR/425167812345/SWIGGY LIMITED/YESB/swiggy8@ybl/Food,4251,03/09/26,340.00,,"84,660.00"',
  '04/09/26,UPI/DR/425167812399/UBER INDIA/YESB/uber.rides@axl/trip,4252,04/09/26,260.00,,"84,400.00"',
].join('\n')

async function register(page, email) {
  await page.context().clearCookies()
  await page.goto('/register')
  await page.getByLabel(/^Email/).fill(email)
  await page.getByLabel(/^Password/).fill(PASSWORD)
  await page.getByLabel(/^Confirm password/).fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: /Hello/ })).toBeVisible()
}

test('landing page scroll sections and 3D hero render', async ({ page }) => {
  await page.context().clearCookies()
  await page.goto('/')
  await expect(page.locator('.landing-3d canvas')).toBeVisible()
  await page.mouse.wheel(0, 1600)
  await expect(page.getByRole('heading', { name: 'From statement to insight in minutes' })).toBeVisible()
  await page.mouse.wheel(0, 1400)
  await expect(page.getByRole('heading', { name: 'AI that learns you' })).toBeVisible()
  await expect(page.getByText('Sample preview – demo data')).toBeVisible()
})

test('forgot password → reset link → sign in with the new password', async ({ page }) => {
  const logPath = process.env.E2E_API_LOG
  test.skip(!logPath, 'Set E2E_API_LOG to the API console log to read the reset link (SMTP not configured)')
  const email = `reset-${Date.now()}@example.com`
  await register(page, email)
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('link', { name: 'Forgot password?' }).click()
  await page.getByLabel(/^Email/).fill(email)
  await page.getByRole('button', { name: 'Send reset link' }).click()
  await expect(page.getByText('Check your inbox')).toBeVisible()
  let link = null
  for (let i = 0; i < 20 && !link; i++) {
    const log = fs.readFileSync(logPath, 'utf-8')
    const matches = [...log.matchAll(/link: (http\S+reset-password\?token=\S+)/g)]
    link = matches.length ? matches[matches.length - 1][1] : null
    if (!link) await page.waitForTimeout(250)
  }
  expect(link).toBeTruthy()
  await page.goto(new URL(link).pathname + new URL(link).search)
  await page.getByLabel(/^New password/).fill('ResetWorks42')
  await page.getByLabel(/^Confirm new password/).fill('ResetWorks42')
  await page.getByRole('button', { name: 'Update password' }).click()
  await expect(page.getByRole('heading', { name: 'Password updated' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel(/^Email/).fill(email)
  await page.getByLabel(/^Password/).fill('ResetWorks42')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /Hello/ })).toBeVisible()
})

test('import a bank CSV in the browser: entities extracted and AI categories applied', async ({ page }) => {
  await register(page, `import-${Date.now()}@example.com`)
  await page.goto('/accounts?new=1')
  await page.getByRole('dialog').getByLabel(/^Name/).fill('HDFC Savings')
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await page.goto('/import')
  await page.locator('input[type=file]').setInputFiles({ name: 'hdfc.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) })
  await page.getByLabel(/Import into account/).selectOption({ label: 'HDFC Savings' })
  await page.getByRole('button', { name: 'Read file' }).click()
  await expect(page.getByText('HDFC Bank')).toBeVisible()
  await page.getByRole('button', { name: 'Validate & check duplicates' }).click()
  await expect(page.getByText('3 new')).toBeVisible()
  await expect(page.getByText('swiggy8@ybl').first()).toBeVisible()
  await page.getByRole('button', { name: 'Import 3 transactions' }).click()
  await expect(page.getByText('Import finished')).toBeVisible()
  await page.goto('/transactions')
  await expect(page.getByRole('cell', { name: /Swiggy/ }).first()).toBeVisible()
  // Imported rows wait for review, so the (auto-chosen) category is shown in a dropdown.
  await expect(page.locator('tr', { hasText: 'Swiggy' }).locator('select option:checked')).toHaveText('Food delivery')
  await expect(page.locator('tr', { hasText: 'Uber' }).locator('select option:checked')).toHaveText('Cab & auto')
  await expect(page.locator('tr', { hasText: 'Swiggy' })).toContainText('swiggy8@ybl')

  // Ask your money (rules engine – no local LLM needed)
  await page.goto('/assistant')
  await page.getByLabel('Question').fill('How much did I earn in September 2026?')
  await page.getByRole('button', { name: 'Ask' }).click()
  await expect(page.locator('.bubble.bot').last()).toContainText('₹85,000')
})
