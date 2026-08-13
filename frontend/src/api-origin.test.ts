import { describe, expect, it } from "vitest"

import { resolveApiBaseUrl } from "./api-origin"

describe("resolveApiBaseUrl", () => {
  it("uses the Firebase Hosting origin when no explicit API base URL is configured", () => {
    expect(resolveApiBaseUrl(undefined, "https://mtg-rules-desk-dev.web.app/", false)).toBe(
      "https://mtg-rules-desk-dev.web.app",
    )
  })

  it("ignores local API overrides in a production build", () => {
    expect(
      resolveApiBaseUrl(
        "http://localhost:8080/",
        "https://mtg-rules-desk-dev.web.app/",
        false,
      ),
    ).toBe("https://mtg-rules-desk-dev.web.app")
  })

  it("uses an explicit local API base URL during development", () => {
    expect(resolveApiBaseUrl("http://localhost:8080/", "https://ignored.example", true)).toBe(
      "http://localhost:8080",
    )
  })
})
