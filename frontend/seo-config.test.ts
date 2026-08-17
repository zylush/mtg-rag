import { describe, expect, it } from "vitest"

import {
  INDEXABLE_ROUTES,
  createPageStructuredData,
  createRobotsTxt,
  createSitemapXml,
  normalizeSiteOrigin,
} from "./seo-config"

const ORIGIN = "https://rules.example.com"

describe("SEO build configuration", () => {
  it("normalizes a safe public origin and rejects ambiguous canonical URLs", () => {
    expect(normalizeSiteOrigin(`${ORIGIN}/`)).toBe(ORIGIN)
    expect(normalizeSiteOrigin("http://localhost:5173")).toBe("http://localhost:5173")
    expect(() => normalizeSiteOrigin("http://rules.example.com")).toThrow(/https/i)
    expect(() => normalizeSiteOrigin(`${ORIGIN}/nested`)).toThrow(/origin/i)
    expect(() => normalizeSiteOrigin("javascript:alert(1)")).toThrow(/https/i)
  })

  it("blocks development crawling and advertises the production sitemap", () => {
    const blocked = createRobotsTxt({ origin: ORIGIN, allowIndexing: false })
    expect(blocked).toMatch(/User-agent: \*\s+Disallow: \//)
    expect(blocked).not.toContain("Sitemap:")

    const publicRobots = createRobotsTxt({ origin: ORIGIN, allowIndexing: true })
    expect(publicRobots).toMatch(/User-agent: \*\s+Allow: \//)
    expect(publicRobots).toContain(`Sitemap: ${ORIGIN}/sitemap.xml`)
  })

  it("lists only canonical public pages in the sitemap", () => {
    const sitemap = createSitemapXml(ORIGIN)

    for (const route of INDEXABLE_ROUTES) {
      expect(sitemap).toContain(`<loc>${ORIGIN}${route}</loc>`)
    }
    expect(sitemap).not.toContain("/desk")
    expect(sitemap).not.toContain("/terms")
    expect(sitemap).not.toContain("/privacy")
  })

  it("describes the free reference application without invented ratings", () => {
    const graph = createPageStructuredData("/", ORIGIN)
    const application = graph?.["@graph"].find(
      (entry) => entry["@type"] === "SoftwareApplication",
    )

    expect(application).toMatchObject({
      name: "MTG Rules Desk",
      applicationCategory: "ReferenceApplication",
      operatingSystem: "Any",
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
    })
    expect(application).not.toHaveProperty("aggregateRating")
    expect(createPageStructuredData("/terms", ORIGIN)).toBeUndefined()
  })
})
