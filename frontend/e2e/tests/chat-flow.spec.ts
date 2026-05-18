import { test, expect } from '../fixtures'

test.describe('Chat Flow', () => {
  test('shows empty state on load', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.messages-empty-title')).toHaveText('AI Mentor')
    await expect(page.locator('.messages-empty-subtitle')).toContainText('Ask me anything')
  })

  test('sends message and receives streaming response', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('.chat-input')
    await input.fill('How to authenticate in HikCentral?')
    await input.press('Enter')

    await expect(page.locator('.message.user')).toBeVisible()
    await expect(page.locator('.message.user .message-content')).toContainText('How to authenticate in HikCentral?')

    await expect(page.locator('.source-card')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.source-card-title')).toContainText('HikCentral API Guide')

    await expect(page.locator('.message.assistant .message-content')).toContainText(
      'This is a mock response from the AI assistant.',
      { timeout: 10000 },
    )

    await expect(page.locator('.message-duration')).toBeVisible({ timeout: 5000 })
  })

  test('SSE tokens appear incrementally', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('.chat-input')
    await input.fill('test streaming')
    await input.press('Enter')

    await expect(page.locator('.streaming-cursor')).toBeVisible({ timeout: 5000 })

    await expect(page.locator('.message.assistant .message-content')).toContainText(
      'This is a mock response',
      { timeout: 10000 },
    )
  })

  test('send button is disabled with empty input', async ({ page }) => {
    await page.goto('/')
    const sendBtn = page.locator('.chat-send-btn')
    await expect(sendBtn).toBeDisabled()
  })

  test('cancel button appears during streaming', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('.chat-input')
    await input.fill('test cancel')
    await input.press('Enter')

    const stopBtn = page.locator('.chat-send-btn[title="Stop generating"]')
    await expect(stopBtn).toBeVisible({ timeout: 3000 })
  })
})
