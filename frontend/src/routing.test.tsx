import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AppLink, normalizeRoute, RouterProvider } from "./routing"

function LinkHarness() {
  return (
    <RouterProvider>
      <AppLink to="/about">About</AppLink>
    </RouterProvider>
  )
}

describe("routing", () => {
  it("normalizes supported, harness, and unknown paths", () => {
    expect(normalizeRoute("/auth")).toBe("/auth")
    expect(normalizeRoute("/login")).toBe("/auth")
    expect(normalizeRoute("/desk")).toBe("/desk")
    expect(normalizeRoute("/desk/history")).toBe("/desk/history")
    expect(normalizeRoute("/desk/settings")).toBe("/desk/settings")
    expect(normalizeRoute("/about")).toBe("/about")
    expect(normalizeRoute("/terms")).toBe("/terms")
    expect(normalizeRoute("/privacy")).toBe("/privacy")
    expect(normalizeRoute("/e2e.html")).toBe("/desk")
    expect(normalizeRoute("/not-a-route")).toBe("/")
  })

  it("replaces an unknown URL with its normalized route", async () => {
    window.history.replaceState({}, "", "/not-a-route")
    render(<LinkHarness />)

    await waitFor(() => expect(window.location.pathname).toBe("/"))
  })

  it("navigates on a primary click and preserves modified clicks", () => {
    window.history.replaceState({}, "", "/")
    render(<LinkHarness />)
    const link = screen.getByRole("link", { name: "About" })

    fireEvent.click(link)
    expect(window.location.pathname).toBe("/about")

    for (const options of [
      { button: 1 },
      { metaKey: true },
      { ctrlKey: true },
      { shiftKey: true },
      { altKey: true },
    ]) {
      window.history.replaceState({}, "", "/")
      fireEvent.click(link, options)
      expect(window.location.pathname).toBe("/")
    }
  })
})
