import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { InstallPromptBanner, useInstallPrompt } from "./InstallPrompt"
import type { InstallPort } from "./types"

function installPort(available = true): InstallPort {
  return {
    available,
    install: vi.fn().mockResolvedValue(true),
  }
}

function Harness({ install }: { install: InstallPort }) {
  const prompt = useInstallPrompt(install)

  return (
    <>
      {prompt.installReady && (
        <button type="button" onClick={() => void prompt.installApp()}>
          Explicit install
        </button>
      )}
      {prompt.showBanner && (
        <InstallPromptBanner
          onDismiss={prompt.dismissBanner}
          onInstall={() => void prompt.installApp()}
        />
      )}
    </>
  )
}

function setStandalone(matches: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches,
    media: "(display-mode: standalone)",
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })
}

beforeEach(() => {
  sessionStorage.clear()
  setStandalone(false)
})

describe("install prompt", () => {
  it("dismisses only the passive banner for the current session", async () => {
    const user = userEvent.setup()
    const install = installPort()
    const first = render(<Harness install={install} />)

    await user.click(screen.getByRole("button", { name: "Dismiss install prompt" }))

    expect(screen.queryByText("Add to home screen")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Explicit install" })).toBeVisible()
    expect(install.install).not.toHaveBeenCalled()

    first.unmount()
    render(<Harness install={install} />)
    expect(screen.queryByText("Add to home screen")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Explicit install" })).toBeVisible()
  })

  it("keeps in-memory dismissal working when session storage is unavailable", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Storage denied", "SecurityError")
    })
    const user = userEvent.setup()

    render(<Harness install={installPort()} />)
    await user.click(screen.getByRole("button", { name: "Dismiss install prompt" }))

    expect(screen.queryByText("Add to home screen")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Explicit install" })).toBeVisible()
    setItem.mockRestore()
  })

  it("suppresses install UI while running as an installed app", () => {
    setStandalone(true)

    render(<Harness install={installPort()} />)

    expect(screen.queryByText("Add to home screen")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Explicit install" })).not.toBeInTheDocument()
  })

  it("clears all install UI after the browser reports installation", () => {
    render(<Harness install={installPort()} />)

    act(() => window.dispatchEvent(new Event("appinstalled")))

    expect(screen.queryByText("Add to home screen")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Explicit install" })).not.toBeInTheDocument()
  })

  it("keeps the retained explicit action usable after banner dismissal", async () => {
    const user = userEvent.setup()
    const install = installPort()
    render(<Harness install={install} />)

    await user.click(screen.getByRole("button", { name: "Dismiss install prompt" }))
    await user.click(screen.getByRole("button", { name: "Explicit install" }))

    expect(install.install).toHaveBeenCalledOnce()
  })
})
