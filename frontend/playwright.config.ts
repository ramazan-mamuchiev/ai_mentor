import { defineConfig, devices } from '@playwright/test'

const MOCK_API_PORT = 3999
const VITE_PORT = 5174

export default defineConfig({
  testDir: './e2e/tests',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://localhost:${VITE_PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: `npx tsx e2e/mock-server.ts`,
      port: MOCK_API_PORT,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npx vite --port ${VITE_PORT}`,
      port: VITE_PORT,
      reuseExistingServer: !process.env.CI,
      env: {
        VITE_API_TARGET: `http://localhost:${MOCK_API_PORT}`,
      },
    },
  ],
})
