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
