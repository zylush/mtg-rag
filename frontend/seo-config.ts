export const DEFAULT_PUBLIC_SITE_ORIGIN = "https://mtg-rules-desk-dev.web.app"

export const INDEXABLE_ROUTES = ["/", "/about"] as const
export type IndexableRoute = (typeof INDEXABLE_ROUTES)[number]
export type SeoShellRoute = IndexableRoute | "/terms" | "/privacy"

export interface SeoPageDefinition {
  title: string
  description: string
  indexable: boolean
}

export interface StructuredDataNode {
  "@type": string
  [key: string]: unknown
}

export interface StructuredDataGraph {
  "@context": "https://schema.org"
  "@graph": StructuredDataNode[]
}

export const SEO_PAGES: Record<SeoShellRoute, SeoPageDefinition> = {
  "/": {
    title: "MTG Rules Desk | Citation-First Magic Rules Answers",
    description:
      "Citation-first Magic: The Gathering answers grounded in the Comprehensive Rules, current Oracle text, and attributed card rulings.",
    indexable: true,
  },
  "/about": {
    title: "How MTG Rules Desk Answers Magic Rules Questions",
    description:
      "See how MTG Rules Desk retrieves Comprehensive Rules, Oracle text, and card rulings to produce focused Magic: The Gathering answers with citations.",
    indexable: true,
  },
  "/terms": {
    title: "Draft Terms of Service | MTG Rules Desk",
    description: "Draft Terms of Service for MTG Rules Desk, pending operator and legal review.",
    indexable: false,
  },
  "/privacy": {
    title: "Privacy Policy | MTG Rules Desk",
    description:
      "Learn how MTG Rules Desk processes account, question, answer, feedback, cache, and operational data.",
    indexable: false,
  },
}

export function normalizeSiteOrigin(value: string): string {
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error("public site URL must be a valid HTTPS origin")
  }

  const localHttp =
    parsed.protocol === "http:" &&
    (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1")
  if (parsed.protocol !== "https:" && !localHttp) {
    throw new Error("public site URL must use HTTPS outside local development")
  }
  if (
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash ||
    parsed.username ||
    parsed.password
  ) {
    throw new Error("public site URL must contain only an origin")
  }
  return parsed.origin
}

export function canonicalUrl(origin: string, route: string): string {
  const normalizedOrigin = normalizeSiteOrigin(origin)
  return route === "/" ? `${normalizedOrigin}/` : `${normalizedOrigin}${route}`
}

export function createRobotsTxt({
  origin,
  allowIndexing,
}: {
  origin: string
  allowIndexing: boolean
}): string {
  const normalizedOrigin = normalizeSiteOrigin(origin)
  if (!allowIndexing) {
    return [
      "# Indexing requires explicit launch approval.",
      "User-agent: *",
      "Disallow: /",
      "",
    ].join("\n")
  }
  return [
    "User-agent: *",
    "Allow: /",
    "",
    `Sitemap: ${normalizedOrigin}/sitemap.xml`,
    "",
  ].join("\n")
}

export function createSitemapXml(origin: string): string {
  const urls = INDEXABLE_ROUTES.map(
    (route) => `  <url>\n    <loc>${canonicalUrl(origin, route)}</loc>\n  </url>`,
  ).join("\n")
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
}

export function createPageStructuredData(
  route: SeoShellRoute | string,
  origin: string,
): StructuredDataGraph | undefined {
  const normalizedOrigin = normalizeSiteOrigin(origin)
  const websiteId = `${normalizedOrigin}/#website`
  const applicationId = `${normalizedOrigin}/#application`

  if (route === "/") {
    return {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebSite",
          "@id": websiteId,
          url: `${normalizedOrigin}/`,
          name: "MTG Rules Desk",
          description: SEO_PAGES["/"].description,
          inLanguage: "en",
        },
        {
          "@type": "SoftwareApplication",
          "@id": applicationId,
          name: "MTG Rules Desk",
          url: `${normalizedOrigin}/`,
          description: SEO_PAGES["/"].description,
          applicationCategory: "ReferenceApplication",
          operatingSystem: "Any",
          browserRequirements: "Requires JavaScript and an internet connection",
          isAccessibleForFree: true,
          inLanguage: "en",
          offers: {
            "@type": "Offer",
            price: "0",
            priceCurrency: "USD",
          },
        },
      ],
    }
  }

  if (route === "/about") {
    return {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebPage",
          "@id": `${canonicalUrl(normalizedOrigin, route)}#webpage`,
          url: canonicalUrl(normalizedOrigin, route),
          name: SEO_PAGES["/about"].title,
          description: SEO_PAGES["/about"].description,
          inLanguage: "en",
          isPartOf: { "@id": websiteId },
          about: { "@id": applicationId },
        },
      ],
    }
  }

  return undefined
}
