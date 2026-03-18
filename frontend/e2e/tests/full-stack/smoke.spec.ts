import { test, expect } from '@playwright/test'

const FULL_STACK_URL = process.env.E2E_BASE_URL || 'http://localhost'

test.describe('Full-stack smoke @slow', () => {
  test.skip(!process.env.E2E_FULL_STACK, 'Set E2E_FULL_STACK=1 to run full-stack tests')

  test('loads the application', async ({ page }) => {
    await page.goto(FULL_STACK_URL)
    await expect(page.locator('.messages-empty-title')).toHaveText('IPCodex AI', { timeout: 15000 })
    await expect(page.locator('.sidebar-title')).toHaveText('IPCodex')
  })

  test('sends a real message and gets LLM response', async ({ page }) => {
    test.setTimeout(120_000)

    await page.goto(FULL_STACK_URL)

    const input = page.locator('.chat-input')
    await input.fill('What is HMAC-SHA256 authentication?')
    await input.press('Enter')

    await expect(page.locator('.message.user')).toBeVisible({ timeout: 5000 })

    await expect(page.locator('.message.assistant .message-content')).not.toBeEmpty({ timeout: 90_000 })

    await expect(page.locator('.message-duration')).toBeVisible({ timeout: 90_000 })
  })

  test('session persists after page reload', async ({ page }) => {
    test.setTimeout(120_000)

    await page.goto(FULL_STACK_URL)

    const input = page.locator('.chat-input')
    await input.fill('Test persistence')
    await input.press('Enter')

    await expect(page.locator('.message-duration')).toBeVisible({ timeout: 90_000 })

    await page.reload()

    await expect(page.locator('.session-item')).toBeVisible({ timeout: 10000 })
    await page.locator('.session-item').first().click()

    await expect(page.locator('.message.user .message-content')).toContainText('Test persistence', { timeout: 10000 })
  })
})
