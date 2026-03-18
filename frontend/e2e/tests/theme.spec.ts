import { test, expect } from '../fixtures'

test.describe('Theme', () => {
  test('toggles between light and dark theme', async ({ page }) => {
    await page.goto('/')

    const html = page.locator('html')
    const initialTheme = await html.getAttribute('data-theme')

    await page.locator('.theme-toggle').click()

    const newTheme = await html.getAttribute('data-theme')
    expect(newTheme).not.toBe(initialTheme)
    expect(['light', 'dark']).toContain(newTheme)

    await page.locator('.theme-toggle').click()

    const restoredTheme = await html.getAttribute('data-theme')
    expect(restoredTheme).toBe(initialTheme)
  })
})
