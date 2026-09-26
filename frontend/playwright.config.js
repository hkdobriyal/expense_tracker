import { defineConfig } from '@playwright/test'

// End-to-end tests drive the real app (API + worker + Vite) in a local browser.
// Start the stack first (scripts/dev.ps1, pointing DATA_DIR at a throwaway folder), then: npx playwright test
// Uses the Edge/Chrome already installed on the machine, so no browser download is needed.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    channel: process.env.E2E_BROWSER_CHANNEL || 'msedge',
    headless: true,
    viewport: { width: 1360, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
