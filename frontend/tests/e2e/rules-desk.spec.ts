import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

async function signIn(page: Page) {
  await page.goto("/e2e.html")
  await page.getByRole("button", { name: "Sign in with Google" }).click()
  await expect(page.getByRole("textbox", { name: "Rules question" })).toBeVisible()
}

async function signInWithFailure(page: Page, failure: "auth" | "network") {
  await page.goto(`/e2e.html?failure=${failure}`)
  await page.getByRole("button", { name: "Sign in with Google" }).click()
  await expect(page.getByRole("textbox", { name: "Rules question" })).toBeVisible()
}

test("signs in, answers from sources, and reports remaining quota", async ({ page }) => {
  await signIn(page)
  await page.getByRole("textbox", { name: "Rules question" }).fill("What blocks flying?")
  await page.getByRole("button", { name: "Ask", exact: true }).click()

  await expect(page.getByText(/only be blocked by creatures with flying/i)).toBeVisible()
  await expect(page.getByText("19 answers left today")).toBeVisible()
  await expect(page.getByRole("link", { name: "Comprehensive Rules 702.9" })).toHaveAttribute(
    "href",
    "https://magic.wizards.com/en/rules#702.9",
  )
})

test("opens and permanently deletes conversation history", async ({ page }) => {
  await signIn(page)
  await page.getByRole("button", { name: "History" }).click()
  await page.getByRole("button", { name: "Flying blockers" }).click()
  await expect(page.getByText("What blocks flying?")).toBeVisible()

  page.once("dialog", (dialog) => dialog.accept())
  await page.getByRole("button", { name: "Delete conversation" }).click()
  await expect(page.getByText("Your answered questions will appear here.")).toBeVisible()
})

test("surfaces quota enforcement without producing an answer", async ({ page }) => {
  await signIn(page)
  await page.getByRole("textbox", { name: "Rules question" }).fill("quota")
  await page.getByRole("button", { name: "Ask", exact: true }).click()

  await expect(page.getByRole("alert")).toContainText("could not complete this answer")
  await expect(page.getByText(/only be blocked/i)).toHaveCount(0)
})

test("shows actionable authentication recovery without provider details", async ({ page }) => {
  await signInWithFailure(page, "auth")
  await page.getByRole("textbox", { name: "Rules question" }).fill("Define a target")
  await page.getByRole("button", { name: "Ask", exact: true }).click()

  await expect(page.getByRole("alert")).toContainText("sign-in session could not be verified")
  await expect(page.getByRole("alert")).not.toContainText("provider")
})

test("does not leave history failures silent", async ({ page }) => {
  await signInWithFailure(page, "network")
  await page.getByRole("button", { name: "History" }).click()

  await expect(page.getByRole("alert")).toContainText("temporarily unreachable")
})

test("requires typed confirmation and signs out after account deletion", async ({ page }) => {
  await signIn(page)
  await page.getByRole("button", { name: "Settings" }).click()
  await page.getByRole("button", { name: "Delete account", exact: true }).click()
  await page.getByRole("textbox", { name: "Type DELETE to confirm" }).fill("DELETE")
  await page.getByRole("button", { name: "Permanently delete account" }).click()

  await expect(page.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
})

test("offers install UI and removes it after the prompt is consumed", async ({ page }) => {
  await signIn(page)
  const install = page.getByRole("button", { name: "Install app" })
  await expect(install).toBeVisible()
  await install.click()
  await expect(install).toHaveCount(0)
})

test("has no detectable WCAG 2.1 AA violations at desktop and mobile widths", async ({ page }) => {
  await signIn(page)
  let results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()
  expect(results.violations).toEqual([])

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible()
  results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()
  expect(results.violations).toEqual([])
})

test("supports keyboard entry and stable layouts at release breakpoints", async ({ page }) => {
  await page.goto("/e2e.html")
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible()
  await page.keyboard.press("Tab")
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeFocused()
  await page.keyboard.press("Enter")
  await page.getByRole("textbox", { name: "Rules question" }).fill("What blocks flying?")
  await page.getByRole("button", { name: "Ask", exact: true }).click()
  await expect(page.getByText(/only be blocked by creatures with flying/i)).toBeVisible()

  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: width === 375 ? 812 : 900 })
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(hasHorizontalOverflow).toBe(false)
    await expect(page).toHaveScreenshot(`rules-desk-${width}.png`, {
      animations: "disabled",
      fullPage: true,
    })
  }
})
