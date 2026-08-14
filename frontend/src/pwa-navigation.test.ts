import { describe, expect, it } from "vitest"

import { NAVIGATION_FALLBACK_DENYLIST } from "../pwa-navigation.ts"

describe("PWA navigation fallback", () => {
  it("never serves the app shell for Firebase auth helper routes", () => {
    expect(NAVIGATION_FALLBACK_DENYLIST.some((pattern) => pattern.test("/__/auth/handler"))).toBe(
      true,
    )
    expect(NAVIGATION_FALLBACK_DENYLIST.some((pattern) => pattern.test("/login"))).toBe(false)
  })
})
