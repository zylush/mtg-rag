import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

async function visit(page: Parameters<typeof test>[0]["page"], route: string) {
  await page.goto(`/e2e.html?route=${encodeURIComponent(route)}`)
}

test("shows a public welcome preview and legal navigation", async ({ page }) => {
  await visit(page, "/")

  await expect(page.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
  await expect(page.getByText("BETA VERSION", { exact: true })).toBeVisible()
  await expect(page.getByText("Question / Answer / Sources", { exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: "Terms of Service" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Privacy Policy" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Support" })).toHaveAttribute(
    "href",
    "mailto:paoloinigo30@gmail.com",
  )
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible()
})

test("answers one public question without an account", async ({ page }) => {
  await visit(page, "/")

  await page.getByRole("textbox", { name: "Your rules question" }).fill("What is flying?")
  await page.getByRole("button", { name: "Ask for free" }).click()

  await expect(page.getByText("Flying creatures can only be blocked by creatures with flying or reach.")).toBeVisible()
  await expect(page.getByText("Public answers are informational")).toBeVisible()
})

test("reveals public sections as they enter the viewport", async ({ page }) => {
  await visit(page, "/")

  const trustRail = page.locator(".source-trust-rail")
  await trustRail.scrollIntoViewIfNeeded()
  await expect(trustRail).toHaveClass(/is-visible/)

  const limitations = page.locator(".public-limitations")
  await limitations.scrollIntoViewIfNeeded()
  await expect(limitations).toHaveClass(/is-visible/)
})

test("smoothly returns to the top when public titles are opened", async ({ page }) => {
  for (const width of [390, 1366]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 768 })
    await visit(page, "/")
    await page.getByRole("link", { name: "About" }).last().scrollIntoViewIfNeeded()
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }))
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0)

    await page.getByRole("link", { name: "About" }).last().click()
    await expect(page).toHaveURL(/\/about$/)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(4)
  }
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
    ["/patch-history", "Patch notes by version."],
  ] as const) {
    await visit(page, route)
    await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
  }
})

test("shows versioned patch releases without authentication", async ({ page }) => {
  await visit(page, "/patch-history")

  await expect(page.getByText("Chronological ledger")).toHaveCount(0)

  await expect(page.getByRole("heading", { name: "Patch notes by version", exact: true })).toBeVisible()
  const order = page.getByRole("combobox", { name: "Patch history order" })
  await expect(order).toHaveValue("newest")
  await expect(page.locator(".patch-release-card").first().getByRole("heading", { level: 3 })).toHaveText(
    "Chat history desk",
  )
  await order.selectOption("oldest")
  await expect(page.locator(".patch-release-card")).toHaveCount(2)
  await expect(page.getByText("Page 1 of 2")).toBeVisible()
  const releasePageTwo = page.getByRole("button", { name: "Go to deployment releases page 2" })
  await releasePageTwo.click()
  await expect(releasePageTwo).toHaveAttribute("aria-current", "page")
  await expect(page.locator(".patch-release-card").first().getByRole("heading", { level: 3 })).toHaveText(
    "Warm preview",
  )
  await expect(page.getByText("Page 2 of 2")).toBeVisible()
  await page.getByRole("button", { name: "Go to deployment releases page 1" }).click()

  const notes = page.getByRole("list", { name: "v0.1.0 patch notes" })
  await expect(notes.getByRole("listitem")).toHaveCount(8)
  const notesPanel = notes.locator("..")
  await expect(notesPanel.getByText(/Page 1 of \d+/)).toBeVisible()
  const firstPageText = await notes.textContent()
  const pageTwo = page.getByRole("button", { name: "Go to v0.1.0 patch notes page 2" })
  await pageTwo.click()
  await expect(pageTwo).toHaveAttribute("aria-current", "page")
  await expect(notesPanel.getByText(/Page 2 of \d+/)).toBeVisible()
  await expect(notes).not.toHaveText(firstPageText ?? "")
  await expect(notes.getByText("e4b2462")).toHaveCount(0)

  await expect(order).toHaveValue("oldest")
  await order.selectOption("newest")
  await expect(page.locator(".patch-release-card").first().getByRole("heading", { level: 3 })).toHaveText(
    "Chat history desk",
  )
})

test("keeps the deployment order filter aligned across viewport sizes", async ({ page }) => {
  for (const width of [390, 1366]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 768 })
    await visit(page, "/patch-history")

    const order = page.getByRole("combobox", { name: "Patch history order" })
    const shell = page.locator(".patch-order-select")
    await expect(shell).toHaveCSS("align-items", "center")
    await expect(order).toHaveCSS("appearance", "none")

    const [selectBox, shellBox] = await Promise.all([order.boundingBox(), shell.boundingBox()])
    expect(selectBox).not.toBeNull()
    expect(shellBox).not.toBeNull()
    expect(Math.abs((selectBox?.height ?? 0) - (shellBox?.height ?? 0))).toBeLessThanOrEqual(1)
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
  for (const route of ["/", "/about", "/terms", "/privacy", "/patch-history"]) {
    await visit(page, route)
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()
    expect(results.violations, `${route} violations`).toEqual([])
  }
})
