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
