import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

async function visit(page: Parameters<typeof test>[0]["page"], route: string) {
  await page.goto(`/e2e.html?route=${encodeURIComponent(route)}`)
}

test("shows a public welcome preview and legal navigation", async ({ page }) => {
  await visit(page, "/")

  await expect(page.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
  await expect(page.getByText(/question.*answer.*sources/i)).toBeVisible()
  await expect(page.getByRole("link", { name: "Terms of Service" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Privacy Policy" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Support" })).toHaveAttribute(
    "href",
    "mailto:paoloinigo30@gmail.com",
  )
  await expect(page.getByRole("link", { name: "Sign in with Google" })).toBeVisible()
})

test("opens About, Terms, and Privacy without authentication", async ({ page }) => {
  for (const [route, heading] of [
    ["/about", "About MTG Rules Desk"],
    ["/terms", "Terms of Service"],
    ["/privacy", "Privacy Policy"],
  ] as const) {
    await visit(page, route)
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible()
  }
})

test("redirects signed-out desk access to auth and returns after sign-in", async ({ page }) => {
  await visit(page, "/desk")

  await expect(page.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
  await expect(page).toHaveURL(/\/auth$/)
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
  for (const route of ["/", "/auth", "/about", "/terms", "/privacy"]) {
    await visit(page, route)
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()
    expect(results.violations, `${route} violations`).toEqual([])
  }
})
