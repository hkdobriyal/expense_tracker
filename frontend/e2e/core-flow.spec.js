import { expect, test } from '@playwright/test'

// Needs a fresh data directory (the first registered user becomes the owner).
const EMAIL = 'owner@example.com'
const PASSWORD = 'E2eStrongPass1'

function trackErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Download the React DevTools/.test(m.text())) errors.push(m.text()) })
  return errors
}

async function addTransaction(page, { type, amount, description, category }) {
  await page.getByRole('button', { name: /^Add/ }).first().click()
  const dialog = page.getByRole('dialog')
  if (type) await dialog.getByRole('button', { name: type, exact: true }).click()
  await dialog.getByLabel('Amount').fill(amount)
  await dialog.getByLabel(/Description/).fill(description)
  if (category) await dialog.getByLabel(/Category/).selectOption({ label: category })
  await dialog.getByRole('button', { name: 'Add transaction' }).click()
  await expect(dialog).toBeHidden()
}

test('sign up → account → income & expense → dashboard → budget alert → notification', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Create your workspace' })).toBeVisible()
  await page.getByLabel('Your name').fill('Owner')
  await page.getByLabel(/Email/).fill(EMAIL)
  await page.getByLabel(/Password/).fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: /Hello, Owner/ })).toBeVisible()
  await expect(page.getByText('Get set up')).toBeVisible()

  // Account
  await page.goto('/accounts?new=1')
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel(/^Name/).fill('HDFC Savings')
  await dialog.getByLabel('Opening balance').fill('10000')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('heading', { name: 'HDFC Savings' })).toBeVisible()
  await expect(page.getByText('₹10,000').first()).toBeVisible()

  // Budget with an 80% alert
  await page.goto('/budgets?new=1')
  const b = page.getByRole('dialog')
  await b.getByLabel(/Category/).selectOption({ label: 'Food (general)' })
  await b.getByLabel(/Limit/).fill('500')
  await b.getByRole('button', { name: 'Save budget' }).click()
  await expect(page.getByText('of ₹500').first()).toBeVisible()

  // Income + expenses
  await page.goto('/')
  await addTransaction(page, { type: 'Income', amount: '50000', description: 'September salary', category: 'Salary (general)' })
  await addTransaction(page, { amount: '390', description: 'DMart groceries', category: 'Groceries' })
  await addTransaction(page, { amount: '20', description: 'Milk', category: 'Groceries' })

  // Dashboard reflects the ledger: 10,000 + 50,000 − 410
  await expect(page.getByText('₹59,590').first()).toBeVisible()

  // Budget page: 82% used
  await page.goto('/budgets')
  await expect(page.getByText('82% · ')).toBeVisible()

  // The budget alert produced an in-app notification
  await page.getByRole('button', { name: /Notifications, 1 unread/ }).click()
  await expect(page.getByText('You have used 82% of your Food budget (₹410 of ₹500).')).toBeVisible()
  await page.keyboard.press('Escape')

  // Alert history shows delivery status per channel
  await page.goto('/alerts?tab=history')
  await expect(page.getByText('Budget warning: Food')).toBeVisible()
  await expect(page.getByText('in-app · sent').first()).toBeVisible()

  // Transactions: search + filter
  await page.goto('/transactions')
  await page.getByLabel('Search transactions').fill('milk')
  await expect(page.getByRole('cell', { name: /Milk/ }).first()).toBeVisible()
  await expect(page.getByText('1 transactions')).toBeVisible()

  // Command palette
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox', { name: 'Search' }).fill('net worth')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/net-worth/)
  await expect(page.getByText('Assets').first()).toBeVisible()

  // Sign out and back in: data persists
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByLabel(/Email/).fill(EMAIL)
  await page.getByLabel(/Password/).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('₹59,590').first()).toBeVisible()

  expect(errors).toEqual([])
})

test('demo workspace: every page renders without errors', async ({ page }) => {
  const errors = trackErrors(page)
  await page.context().clearCookies()
  await page.goto('/')
  await page.getByRole('button', { name: 'Try the demo workspace' }).click()
  await expect(page.getByText(/DEMO WORKSPACE/)).toBeVisible()
  const pages = ['/', '/transactions', '/accounts', '/categories', '/budgets', '/goals', '/bills', '/subscriptions', '/recurring', '/analytics', '/cash-flow', '/net-worth', '/reports', '/banks', '/import', '/alerts', '/alerts?tab=history', '/settings']
  for (const path of pages) {
    await page.goto(path)
    await expect(page.locator('main')).toBeVisible()
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Something went wrong')).toHaveCount(0)
  }
  // Sync now on the sandbox bank reports real counts
  await page.goto('/banks')
  await page.getByRole('button', { name: 'Sync now' }).click()
  await expect(page.getByRole('heading', { name: 'Synchronisation completed' })).toBeVisible()
  await expect(page.getByText('duplicates skipped', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()
  // Mobile layout
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: 'Quick navigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Exit demo' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect(errors).toEqual([])
})
