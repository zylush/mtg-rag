import { describe, expect, it } from "vitest"

import { createFirebaseConfig } from "./firebase-config"

const environment = {
  VITE_FIREBASE_API_KEY: "public-browser-key",
  VITE_FIREBASE_AUTH_DOMAIN: "mtg-rules-desk-dev.firebaseapp.com",
  VITE_FIREBASE_PROJECT_ID: "mtg-rules-desk-dev",
  VITE_FIREBASE_APP_ID: "firebase-app-id",
}

describe("Firebase browser configuration", () => {
  it("keeps the auth helper on the Firebase Hosting origin", () => {
    expect(
      createFirebaseConfig(environment, "mtg-rules-desk-dev.web.app").authDomain,
    ).toBe("mtg-rules-desk-dev.web.app")
  })

  it("keeps the configured auth domain outside the default web.app host", () => {
    expect(createFirebaseConfig(environment, "localhost").authDomain).toBe(
      "mtg-rules-desk-dev.firebaseapp.com",
    )
  })
})
