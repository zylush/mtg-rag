import { describe, expect, it } from "vitest"

import { resolveApiBaseUrl } from "./api-origin"

describe("resolveApiBaseUrl", () => {
  it("uses the Firebase Hosting origin when no explicit API base URL is configured", () => {
    expect(resolveApiBaseUrl(undefined, "https://mtg-rules-desk-dev.web.app/")).toBe(
      "https://mtg-rules-desk-dev.web.app",
    )
  })

  it("uses an explicit local API base URL during development", () => {
    expect(resolveApiBaseUrl("http://localhost:8080/", "https://ignored.example")).toBe(
      "http://localhost:8080",
    )
  })
})
