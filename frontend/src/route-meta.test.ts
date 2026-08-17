import { describe, expect, it } from "vitest"

import { applyRouteMetadata, getRouteMetadata } from "./route-meta"

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
    expect(home.image).toBe(`${ORIGIN}/pwa-512x512.png`)
    expect(home.structuredData?.["@graph"]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ "@type": "WebSite" }),
        expect.objectContaining({ "@type": "SoftwareApplication" }),
      ]),
    )
  })

  it("keeps development, authenticated, login, and draft legal routes out of search", () => {
    expect(getRouteMetadata("/", { origin: ORIGIN, allowIndexing: false }).robots).toBe(
      "noindex, nofollow",
    )

    for (const route of [
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

  it("applies canonical, social, and structured metadata and clears stale schema", () => {
    const home = getRouteMetadata("/", { origin: ORIGIN, allowIndexing: true })
    applyRouteMetadata(home)

    expect(document.title).toBe(home.title)
    expect(document.head.querySelector('meta[property="og:title"]')).toHaveAttribute(
      "content",
      home.title,
    )
    expect(document.head.querySelector('meta[property="og:url"]')).toHaveAttribute(
      "content",
      home.canonical,
    )
    expect(document.head.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary",
    )
    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute(
      "href",
      home.canonical,
    )

    const structuredData = document.head.querySelector<HTMLScriptElement>(
      'script[type="application/ld+json"][data-route-seo]',
    )
    expect(JSON.parse(structuredData?.textContent ?? "{}")).toEqual(home.structuredData)

    applyRouteMetadata(
      getRouteMetadata("/desk", { origin: ORIGIN, allowIndexing: true }),
    )
    expect(
      document.head.querySelector('script[type="application/ld+json"][data-route-seo]'),
    ).not.toBeInTheDocument()
  })
})
