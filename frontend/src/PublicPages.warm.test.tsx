import { render, screen } from "@testing-library/react"
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
    expect(screen.getByText("155 commits recorded")).toBeVisible()
    expect(screen.getByText("3e50395")).toBeVisible()
    expect(screen.getByText(/docs: record chat history verification checkpoints/i)).toBeVisible()
    expect(screen.getAllByRole("listitem")).toHaveLength(155)
  })
})
