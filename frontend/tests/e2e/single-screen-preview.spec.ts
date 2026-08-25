import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

test("single-screen command desk stays usable at release widths", async ({ page }, testInfo) => {
  await page.goto("/e2e.html")
  await page.getByRole("button", { name: "Sign in with Google" }).click()

  const input = page.getByRole("textbox", { name: "Rules question" })
  await expect(input).toBeFocused()
  await expect(page.getByText("Retrieval online")).toBeVisible()

  await page.getByRole("button", { name: /Blood Moon.*Urza's Saga/i }).click()
  await expect(input).toHaveValue("How does Blood Moon interact with Urza's Saga?")
  await page.getByRole("button", { name: "Ask", exact: true }).click()
  await expect(page.getByText(/only be blocked by creatures with flying/i)).toBeVisible()
  await expect(page.getByText(/grounded in retrieved rules sources/i)).toBeVisible()

  for (const width of [320, 375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: width < 700 ? 812 : 900 })
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(hasHorizontalOverflow).toBe(false)
    await expect(page.getByRole("textbox", { name: "Rules question" })).toBeVisible()
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible()
    if ([375, 768, 1440].includes(width)) {
      await page.screenshot({
        path: testInfo.outputPath(`single-screen-${width}.png`),
        fullPage: true,
        animations: "disabled",
      })
    }
  }

  await page.setViewportSize({ width: 375, height: 812 })
  await expect(page.getByText("Keep the rules desk close")).toBeVisible()
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze()
  expect(results.violations).toEqual([])
})

test("mobile install banner can be dismissed without losing the explicit install action", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto("/e2e.html")
  await page.getByRole("button", { name: "Sign in with Google" }).click()

  await expect(page.getByText("Keep the rules desk close")).toBeVisible()
  await page.getByRole("button", { name: "Dismiss install prompt" }).click()
  await expect(page.getByText("Keep the rules desk close")).toBeHidden()

  await page.getByRole("button", { name: "Settings" }).click()
  await expect(page.getByRole("button", { name: "Install app" })).toBeVisible()

  await page.goto("/e2e.html")
  await page.getByRole("button", { name: "Sign in with Google" }).click()
  await expect(page.getByText("Keep the rules desk close")).toBeHidden()
})

test("public reference screens stay inside mobile viewports", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" })

  for (const route of ["/", "/about", "/patch-history", "/terms", "/privacy"]) {
    await page.setViewportSize({ width: 320, height: 780 })
    await page.goto(`/e2e.html?route=${encodeURIComponent(route)}`)
    await expect(page.getByRole("link", { name: "MTG Rules Desk home" })).toBeVisible()

    const dimensions = await page.evaluate(() => ({
      body: document.body.scrollWidth,
      document: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }))
    expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport)
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport)

    if (route === "/") {
      await expect(page.locator(".ledger-typing-line").first()).toHaveCSS(
        "animation-name",
        "ledger-type-on",
      )
      await expect(page.locator(".ledger-typing-line").first()).toHaveCSS(
        "animation-iteration-count",
        "1",
      )
      await expect(page.locator(".ledger-stack")).toHaveCSS(
        "animation-name",
        "ledger-stack-settle",
      )
      await expect(page.locator(".ledger-sheet-back")).toHaveCSS(
        "animation-name",
        "ledger-back-drift",
      )
    }
  }

  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.goto("/e2e.html?route=/")
  await expect(page.locator(".ledger-typing-line").first()).toHaveCSS("animation-name", "none")
})
