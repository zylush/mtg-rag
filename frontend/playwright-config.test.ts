import { describe, expect, it } from "vitest"

import config from "./playwright.config"

describe("Playwright release configuration", () => {
  it("uses a contention-tolerant test budget without automatic retries", () => {
    expect(config.timeout).toBe(60_000)
    expect(config.retries).toBe(0)
    expect(config.workers).toBe(1)
  })
})
