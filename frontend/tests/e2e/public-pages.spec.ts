import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

async function visit(page: Parameters<typeof test>[0]["page"], route: string) {
  await page.goto(`/e2e.html?route=${encodeURIComponent(route)}`)
}

test("shows a public welcome preview and legal navigation", async ({ page }) => {
  await visit(page, "/")

  await expect(page.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
  await expect(page.getByText("Question / Answer / Sources", { exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: "Terms of Service" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Privacy Policy" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Support" })).toHaveAttribute(
    "href",
    "mailto:paoloinigo30@gmail.com",
  )
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible()
})

test("welcome screen keeps its warm identity and hierarchy at release widths", async ({ page }, testInfo) => {
  for (const width of [320, 375, 430, 768, 1024, 1366, 1440]) {
    const height = width < 700 ? 812 : width === 768 ? 1024 : 900
    await page.setViewportSize({ width, height })
    await visit(page, "/")

    const signIn = page.getByRole("button", { name: "Sign in with Google" })
    await expect(signIn).toBeVisible()
    await expect(page.locator("[data-brand-mark]")).toBeVisible()
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(hasHorizontalOverflow, "horizontal overflow at " + width + "px").toBe(false)

    if (width === 1366) {
      const actionBox = await signIn.boundingBox()
      expect(actionBox).not.toBeNull()
      expect(actionBox.y + actionBox.height).toBeLessThanOrEqual(768)
    }

    if ([375, 768, 1366, 1440].includes(width)) {
      await page.screenshot({
        path: testInfo.outputPath("warm-welcome-" + width + ".png"),
        fullPage: true,
        animations: "disabled",
      })
    }
  }

  await page.setViewportSize({ width: 1366, height: 768 })
  await visit(page, "/")
  await expect(page.locator(".public-site")).toHaveCSS("background-color", "rgb(23, 18, 15)")
  await expect(page.locator(".public-site")).toHaveCSS("background-image", "none")
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toHaveCSS(
    "background-color",
    "rgb(184, 74, 47)",
  )
  const faviconResponse = await page.request.get("/favicon.svg")
  expect(faviconResponse.ok()).toBe(true)
  const favicon = (await faviconResponse.text()).toLowerCase()
  expect(favicon).toContain("#17120f")
  expect(favicon).toContain("#c89b4b")
})

test("opens About, Terms, and Privacy without authentication", async ({ page }) => {
  for (const [route, heading] of [
    ["/about", "About MTG Rules Desk"],
    ["/terms", "Terms of Service"],
    ["/privacy", "Privacy Policy"],
  ] as const) {
    await visit(page, route)
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
  }
})

test("redirects signed-out desk access home and starts auth from the first screen", async ({ page }) => {
  await visit(page, "/desk")

  await expect(page.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
  await page.getByRole("button", { name: "Sign in with Google" }).click()
  await expect(page.getByRole("textbox", { name: "Rules question" })).toBeVisible()
  await expect(page).toHaveURL(/\/desk$/)
})

test("normalizes unknown routes and applies development-safe metadata", async ({ page }) => {
  await visit(page, "/not-a-route")

  await expect(page).toHaveURL(/\/$/)
  await expect(page).toHaveTitle("MTG Rules Desk | Citation-First Magic Rules Answers")
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
    "content",
    "noindex, nofollow",
  )
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/$/)
})

test("public pages have no detectable WCAG violations", async ({ page }) => {
  for (const route of ["/", "/about", "/terms", "/privacy"]) {
    await visit(page, route)
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()
    expect(results.violations, `${route} violations`).toEqual([])
  }
})
