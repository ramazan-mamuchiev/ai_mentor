import { test, expect } from '../fixtures'

test.describe('Session Management', () => {
  test('creates new session via New Chat button', async ({ page }) => {
    await page.goto('/')

    await page.locator('.new-chat-btn').click()

    await expect(page.locator('.session-item')).toHaveCount(1, { timeout: 3000 })
  })

  test('session appears in sidebar after sending message', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('.chat-input')
    await input.fill('Hello AI')
    await input.press('Enter')

    await expect(page.locator('.message.assistant .message-content')).toContainText(
      'mock response',
      { timeout: 10000 },
    )

    await expect(page.locator('.session-item')).toBeVisible({ timeout: 3000 })
    await expect(page.locator('.session-item-title')).toContainText('Hello AI')
  })

  test('switching sessions loads message history', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('.chat-input')
    await input.fill('First message')
    await input.press('Enter')
    await expect(page.locator('.message-duration')).toBeVisible({ timeout: 10000 })

    await page.locator('.new-chat-btn').click()
    await expect(page.locator('.message.user')).toHaveCount(0, { timeout: 5000 })

    await page.locator('.session-item-title', { hasText: 'First message' }).click()
    await expect(page.locator('.message.user .message-content')).toContainText('First message', { timeout: 5000 })
  })

  test('deleting session removes it from sidebar', async ({ page }) => {
    await page.goto('/')

    await page.locator('.new-chat-btn').click()
    await expect(page.locator('.session-item')).toHaveCount(1, { timeout: 3000 })

    await page.locator('.session-item').hover()
    await page.locator('.session-delete-btn').click()

    await expect(page.locator('.session-item')).toHaveCount(0, { timeout: 3000 })
  })
})
