import { defineConfig, devices } from "@playwright/test"

const e2ePort = Number(process.env.E2E_PORT ?? "4173")
if (!Number.isInteger(e2ePort) || e2ePort < 1024 || e2ePort > 65_535) {
  throw new Error("E2E_PORT must be an integer from 1024 through 65535")
}
const e2eOrigin = `http://127.0.0.1:${e2ePort}`

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 2,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: e2eOrigin,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 7"] },
    },
    {
      name: "mobile-safari",
      use: { ...devices["iPhone 15"] },
    },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${e2ePort}`,
    url: `${e2eOrigin}/e2e.html`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
