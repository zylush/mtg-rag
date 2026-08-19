import { X } from "lucide-react"
import { useEffect, useState } from "react"

import type { InstallPort } from "./types"

const DISMISSED_KEY = "mtg-install-banner-dismissed"

function isStandaloneDisplayMode(): boolean {
  if (typeof window === "undefined") return false
  const displayMode = window.matchMedia?.("(display-mode: standalone)").matches ?? false
  const navigatorWithStandalone = navigator as Navigator & { standalone?: boolean }
  return displayMode || navigatorWithStandalone.standalone === true
}

function readSessionDismissal(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISSED_KEY) === "true"
  } catch {
    return false
  }
}

export function useInstallPrompt(install: InstallPort) {
  const [installReady, setInstallReady] = useState(
    () => install.available && !isStandaloneDisplayMode(),
  )
  const [bannerDismissed, setBannerDismissed] = useState(readSessionDismissal)

  useEffect(() => {
    const displayMode = window.matchMedia?.("(display-mode: standalone)")
    const syncAvailability = () => {
      setInstallReady(!isStandaloneDisplayMode() && install.available)
    }
    const markInstalled = () => setInstallReady(false)

    window.addEventListener("mtg-install-ready", syncAvailability)
    window.addEventListener("appinstalled", markInstalled)
    displayMode?.addEventListener?.("change", syncAvailability)
    syncAvailability()

    return () => {
      window.removeEventListener("mtg-install-ready", syncAvailability)
      window.removeEventListener("appinstalled", markInstalled)
      displayMode?.removeEventListener?.("change", syncAvailability)
    }
  }, [install])

  const dismissBanner = () => {
    setBannerDismissed(true)
    try {
      window.sessionStorage.setItem(DISMISSED_KEY, "true")
    } catch {
      // The state update above preserves dismissal when storage is unavailable.
    }
  }

  const installApp = async () => {
    const accepted = await install.install()
    if (accepted || !install.available) setInstallReady(false)
    return accepted
  }

  return {
    installReady,
    showBanner: installReady && !bannerDismissed,
    dismissBanner,
    installApp,
  }
}

export function InstallPromptBanner({
  onDismiss,
  onInstall,
}: {
  onDismiss: () => void
  onInstall: () => void
}) {
  return (
    <aside className="mobile-install-banner" aria-label="Install MTG Rules Desk">
      <div className="install-banner-copy">
        <strong>Keep the rules desk close</strong>
        <span>Install the app shell for quick access. Live answers still need internet.</span>
      </div>
      <div className="install-banner-actions">
        <button className="install-banner-action" type="button" onClick={onInstall}>
          Add to home screen
        </button>
        <button
          aria-label="Dismiss install prompt"
          className="install-banner-dismiss"
          type="button"
          onClick={onDismiss}
        >
          <X aria-hidden="true" size={18} />
        </button>
      </div>
    </aside>
  )
}
