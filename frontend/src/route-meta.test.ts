import { describe, expect, it } from "vitest"

import { getRouteMetadata } from "./route-meta"

const ORIGIN = "https://mtg-rules-desk-dev.web.app"

describe("route metadata", () => {
  it("describes public pages with unique canonical metadata", () => {
    const home = getRouteMetadata("/", { origin: ORIGIN, allowIndexing: true })
    const about = getRouteMetadata("/about", { origin: ORIGIN, allowIndexing: true })

    expect(home.title).toBe("MTG Rules Desk | Citation-First Magic Rules Answers")
    expect(home.description).toMatch(/comprehensive rules.*oracle text/i)
    expect(home.canonical).toBe(`${ORIGIN}/`)
    expect(home.robots).toBe("index, follow")
    expect(about.title).not.toBe(home.title)
    expect(about.description).not.toBe(home.description)
    expect(about.canonical).toBe(`${ORIGIN}/about`)
  })

  it("keeps development, authenticated, login, and draft legal routes out of search", () => {
    expect(getRouteMetadata("/", { origin: ORIGIN, allowIndexing: false }).robots).toBe(
      "noindex, nofollow",
    )

    for (const route of [
      "/login",
      "/desk",
      "/desk/history",
      "/desk/settings",
      "/terms",
      "/privacy",
    ] as const) {
      const metadata = getRouteMetadata(route, { origin: ORIGIN, allowIndexing: true })
      expect(metadata.robots, route).toBe("noindex, nofollow")
      expect(metadata.canonical, route).toBe(`${ORIGIN}${route}`)
    }
  })
})
