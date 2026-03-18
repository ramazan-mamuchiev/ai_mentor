import { test as base } from '@playwright/test'

const MOCK_API = 'http://localhost:3999'

export const test = base.extend({
  page: async ({ page }, use) => {
    try {
      await fetch(`${MOCK_API}/api/v1/e2e/reset`, { method: 'POST' })
    } catch {
      // mock server might not be running for full-stack tests
    }
    await use(page)
  },
})

export { expect } from '@playwright/test'
