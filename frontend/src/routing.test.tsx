import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

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
    expect(normalizeRoute("/auth")).toBe("/")
    expect(normalizeRoute("/login")).toBe("/")
    expect(normalizeRoute("/desk")).toBe("/desk")
    expect(normalizeRoute("/desk/history")).toBe("/desk/history")
    expect(normalizeRoute("/desk/settings")).toBe("/desk/settings")
    expect(normalizeRoute("/about")).toBe("/about")
    expect(normalizeRoute("/terms")).toBe("/terms")
    expect(normalizeRoute("/privacy")).toBe("/privacy")
    expect(normalizeRoute("/patch-history")).toBe("/patch-history")
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

  it("smoothly returns to the top when a route changes", async () => {
    window.history.replaceState({}, "", "/")
    Object.defineProperty(window, "scrollY", { configurable: true, value: 320 })
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
    render(<LinkHarness />)

    fireEvent.click(screen.getByRole("link", { name: "About" }))

    await waitFor(() =>
      expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" }),
    )
    scrollTo.mockRestore()
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 })
  })

  it("uses an instant top reset when reduced motion is requested", async () => {
    window.history.replaceState({}, "", "/")
    Object.defineProperty(window, "scrollY", { configurable: true, value: 320 })
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
    const matchMedia = vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })
    render(<LinkHarness />)

    fireEvent.click(screen.getByRole("link", { name: "About" }))

    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" }))
    matchMedia.mockRestore()
    scrollTo.mockRestore()
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 })
  })
})
