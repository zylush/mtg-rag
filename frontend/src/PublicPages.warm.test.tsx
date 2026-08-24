import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { PatchHistoryPage, WelcomePage } from "./PublicPages"
import { RouterProvider } from "./routing"

function renderWelcome(props: Parameters<typeof WelcomePage>[0] = {}) {
  window.history.replaceState({}, "", "/")
  return render(
    <RouterProvider>
      <WelcomePage {...props} />
    </RouterProvider>,
  )
}

describe("Ember Archive welcome screen", () => {
  it("presents the warm citation-first welcome hierarchy and shared mark", () => {
    const { container } = renderWelcome()

    expect(screen.getByText("Public development preview")).toBeVisible()
    expect(screen.getByText("Rules answers with receipts")).toBeVisible()
    expect(
      screen.getByRole("heading", { name: "Settle the ruling. Keep the game moving." }),
    ).toBeVisible()
    expect(screen.getByText(/your api key stays on the server/i)).toBeVisible()
    expect(screen.getByText("Comprehensive Rules")).toBeVisible()
    expect(screen.getByText("Oracle text")).toBeVisible()
    expect(screen.getByText("Official rulings")).toBeVisible()
    expect(container.querySelector("[data-brand-mark]")).toBeInTheDocument()
  })

  it("keeps the required Wizards notice alongside the preview label", () => {
    renderWelcome()

    expect(screen.getByText("Public development preview")).toBeVisible()
    expect(
      screen.getByText(/unofficial fan content permitted under the fan content policy/i),
    ).toBeVisible()
    expect(screen.getByText(/not approved or endorsed by wizards of the coast/i)).toBeVisible()
  })

  it("preserves the Google sign-in action and pending state", async () => {
    const user = userEvent.setup()
    const onSignIn = vi.fn()
    const view = renderWelcome({ onSignIn })

    await user.click(screen.getByRole("button", { name: "Sign in with Google" }))
    expect(onSignIn).toHaveBeenCalledOnce()

    view.rerender(
      <RouterProvider>
        <WelcomePage onSignIn={onSignIn} signingIn />
      </RouterProvider>,
    )
    expect(screen.getByRole("button", { name: "Signing you in..." })).toBeDisabled()
  })

  it("preserves actionable sign-in failure feedback", () => {
    renderWelcome({ signInError: true })

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sign-in did not complete. Check popup permissions and try again.",
    )
  })

  it("offers a free public question without requiring sign-in", async () => {
    const user = userEvent.setup()
    const onPublicAsk = vi.fn().mockResolvedValue({
      conversation_id: "conversation-public",
      message_id: "message-public",
      answer: "Flying restricts which creatures can block.",
      citations: [],
      assumptions: [],
      confidence: "high",
      needs_clarification: false,
      quota_remaining: 0,
      cache_status: "miss",
    })
    renderWelcome({ onPublicAsk })

    await user.type(
      screen.getByRole("textbox", { name: "Your rules question" }),
      "What is flying?",
    )
    await user.click(screen.getByRole("button", { name: "Ask for free" }))

    expect(await screen.findByText("Flying restricts which creatures can block.")).toBeVisible()
    expect(onPublicAsk).toHaveBeenCalledWith("What is flying?")
  })
})

describe("patch history page", () => {
  it("shows the complete captured ledger with release context", () => {
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    expect(
      screen.getByRole("heading", { name: "Every patch, with a paper trail." }),
    ).toBeVisible()
    expect(screen.getByText("162 commits recorded")).toBeVisible()
    expect(screen.getAllByText("49873ff")).toHaveLength(3)
    expect(screen.getAllByText("Record chat history verification checkpoints")).toHaveLength(2)
    expect(screen.queryByText(/docs: record chat history verification checkpoints/i)).not.toBeInTheDocument()
    expect(document.querySelectorAll(".patch-day .patch-entry")).toHaveLength(162)
  })

  it("compacts date sections and reorders the ledger", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    const order = screen.getByRole("combobox", { name: "Patch history order" })
    expect(order).toHaveValue("oldest")
    expect(screen.getByRole("heading", { name: "Aug 12, 2026" })).toBeVisible()

    await user.selectOptions(order, "newest")
    expect(screen.getByRole("heading", { name: "Aug 25, 2026" })).toBeVisible()
    expect(screen.getByText(/^\d+ Feature/)).toBeVisible()

    const collapse = screen.getByRole("button", {
      name: "Collapse August 25, 2026 patches",
    })
    await user.click(collapse)
    expect(collapse).toHaveAttribute("aria-expanded", "false")
    const collapsedList = document.getElementById("patch-list-2026-08-25")
    expect(collapsedList).not.toBeNull()
    expect(collapsedList).toHaveAttribute("hidden")
  })

  it("groups patch notes by deployment and paginates each release", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    expect(screen.getByRole("heading", { name: "Patch notes by version" })).toBeVisible()
    expect(screen.getByRole("heading", { name: "First hosted preview" })).toBeVisible()
    expect(screen.getByText("Deployed 2026-08-13")).toBeVisible()
    expect(
      screen.getByRole("link", { name: "v0.1.0 checkpoint bd44b3a" }),
    ).toHaveAttribute("href", "https://github.com/zylush/mtg-rag/commit/bd44b3a")

    const notes = screen.getByRole("list", { name: "v0.1.0 patch notes" })
    expect(within(notes).getAllByRole("listitem")).toHaveLength(8)
    expect(screen.getByText("Page 1 of 12")).toBeVisible()

    const pageTwo = screen.getByRole("button", {
      name: "Go to v0.1.0 patch notes page 2",
    })
    await user.click(pageTwo)
    expect(pageTwo).toHaveAttribute("aria-current", "page")
    expect(screen.getByText("Page 2 of 12")).toBeVisible()
    expect(within(notes).getByText("e4b2462")).toBeVisible()
  })
})
