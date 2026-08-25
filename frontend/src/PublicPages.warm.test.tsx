import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { PatchHistoryPage, WelcomePage } from "./PublicPages"
import { RouterProvider } from "./routing"
import type { AskResponse } from "./types"

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

    expect(screen.getByText("BETA VERSION")).toBeVisible()
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

  it("keeps the ledger copy accessible while sequencing its question, answer, and sources", () => {
    const { container } = renderWelcome()

    expect(container.querySelectorAll(".ledger-typing-line")).toHaveLength(4)
    expect(container.querySelector('[data-ledger-stage="question"]')).toHaveTextContent(
      "If a spell loses its only target",
    )
    expect(container.querySelector('[data-ledger-stage="answer"]')).toHaveTextContent(
      "The spell does not resolve",
    )
    expect(container.querySelector('[data-ledger-stage="source"]')).toHaveTextContent(
      "CR 608.2b",
    )
  })

  it("marks below-fold welcome sections as revealed when observers are unavailable", async () => {
    const { container } = renderWelcome({ onPublicAsk: vi.fn() })

    await waitFor(() => {
      expect(container.querySelectorAll("[data-scroll-reveal]")).toHaveLength(3)
      expect(container.querySelectorAll("[data-scroll-reveal].is-visible")).toHaveLength(3)
    })
  })

  it("keeps the required Wizards notice alongside the beta label", () => {
    renderWelcome()

    expect(screen.getByText("BETA VERSION")).toBeVisible()
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

  it("shows an accessible answer skeleton while a public question is pending", async () => {
    const user = userEvent.setup()
    const onPublicAsk = vi.fn(
      () => new Promise<AskResponse>(() => undefined),
    )
    renderWelcome({ onPublicAsk })

    await user.type(
      screen.getByRole("textbox", { name: "Your rules question" }),
      "What is flying?",
    )
    await user.click(screen.getByRole("button", { name: "Ask for free" }))

    const loading = await screen.findByRole("status", {
      name: /checking public rules question/i,
    })
    expect(loading).toBeVisible()
    expect(document.querySelector(".public-ask-panel")).toHaveAttribute("aria-busy", "true")
    expect(loading.querySelectorAll(".public-ask-skeleton .shimmer")).toHaveLength(3)
  })
})

describe("patch history page", () => {
  it("shows versioned releases without a chronological ledger", () => {
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    expect(
      screen.getByRole("heading", { name: "Patch notes by version." }),
    ).toBeVisible()
    expect(screen.queryByText("Chronological ledger")).not.toBeInTheDocument()
    expect(document.querySelectorAll(".patch-day, .patch-entry")).toHaveLength(0)
    expect(screen.queryByText("49873ff")).not.toBeInTheDocument()
  })

  it("merges related changes into concise multi-sentence notes", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    await user.selectOptions(screen.getByRole("combobox", { name: "Patch history order" }), "oldest")
    const notes = screen.getByRole("list", { name: "v0.1.0 patch notes" })
    const noteItems = within(notes).getAllByRole("listitem")

    expect(noteItems[1]).toHaveTextContent(
      /Define persistence and ingestion safety contracts.*Add immutable corpus persistence contracts/,
    )
    for (const note of noteItems) {
      expect(note.textContent?.match(/[^.!?]+[.!?]+/g)?.length ?? 0).toBeGreaterThanOrEqual(2)
    }
  })

  it("reorders deployment releases", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/patch-history")
    render(
      <RouterProvider>
        <PatchHistoryPage />
      </RouterProvider>,
    )

    const order = screen.getByRole("combobox", { name: "Patch history order" })
    expect(order).toHaveValue("newest")
    expect(screen.getAllByRole("heading", { level: 3 })[0]).toHaveTextContent("Chat history desk")

    await user.selectOptions(order, "oldest")
    expect(screen.getAllByRole("heading", { level: 3 })[0]).toHaveTextContent("First hosted preview")
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
    const order = screen.getByRole("combobox", { name: "Patch history order" })
    expect(order).toHaveValue("newest")
    expect(screen.getByRole("heading", { name: "Chat history desk" })).toBeVisible()
    await user.selectOptions(order, "oldest")
    expect(screen.getByRole("heading", { name: "First hosted preview" })).toBeVisible()
    expect(screen.getByText("Deployed 2026-08-13")).toBeVisible()
    expect(document.querySelectorAll(".patch-release-card")).toHaveLength(2)
    expect(screen.queryByText("Git proof")).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "v0.1.0 checkpoint bd44b3a" })).not.toBeInTheDocument()
    expect(screen.getByText("Page 1 of 2")).toBeVisible()

    const releasePageTwo = screen.getByRole("button", {
      name: "Go to deployment releases page 2",
    })
    await user.click(releasePageTwo)
    expect(releasePageTwo).toHaveAttribute("aria-current", "page")
    expect(screen.getByRole("heading", { name: "Warm preview" })).toBeVisible()
    expect(screen.getByText("Page 2 of 2")).toBeVisible()

    await user.click(screen.getByRole("button", { name: "Go to deployment releases page 1" }))

    const notes = screen.getByRole("list", { name: "v0.1.0 patch notes" })
    const noteItems = within(notes).getAllByRole("listitem")
    expect(noteItems).toHaveLength(8)
    for (const note of noteItems) {
      expect(note.textContent?.match(/[^.!?]+[.!?]+/g)?.length ?? 0).toBeGreaterThanOrEqual(2)
    }
    const notesPanel = notes.closest(".patch-notes-panel")
    expect(notesPanel).not.toBeNull()
    expect(within(notesPanel as HTMLElement).getByText(/Page 1 of \d+/)).toBeVisible()
    const firstPageText = notes.textContent

    const pageTwo = screen.getByRole("button", {
      name: "Go to v0.1.0 patch notes page 2",
    })
    await user.click(pageTwo)
    expect(pageTwo).toHaveAttribute("aria-current", "page")
    expect(within(notesPanel as HTMLElement).getByText(/Page 2 of \d+/)).toBeVisible()
    expect(notes).not.toHaveTextContent(firstPageText ?? "")
    expect(within(notes).queryByText("e4b2462")).not.toBeInTheDocument()
  })
})
