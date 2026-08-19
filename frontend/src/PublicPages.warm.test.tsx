import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { WelcomePage } from "./PublicPages"
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
})
