import type { AppRoute } from "./routing"
import {
  SEO_PAGES,
  canonicalUrl,
  createPageStructuredData,
  normalizeSiteOrigin,
  type StructuredDataGraph,
} from "../seo-config"

export interface RouteMetadata {
  title: string
  description: string
  canonical: string
  robots: "index, follow" | "noindex, nofollow"
  image: string
  structuredData?: StructuredDataGraph
}

interface MetadataOptions {
  origin: string
  allowIndexing: boolean
}

const descriptions: Record<AppRoute, string> = {
  "/": SEO_PAGES["/"].description,
  "/desk": "Ask a grounded Magic: The Gathering rules question and review its citations.",
  "/desk/history": "Review saved MTG Rules Desk conversations.",
  "/desk/settings": "Manage MTG Rules Desk product links, installation, and account controls.",
  "/about": SEO_PAGES["/about"].description,
  "/patch-history":
    "Review versioned patch notes for the MTG Rules Desk development preview.",
  "/terms": "Operational Terms of Service for MTG Rules Desk, with source attribution and support contact.",
  "/privacy": SEO_PAGES["/privacy"].description,
}

const titles: Record<AppRoute, string> = {
  "/": SEO_PAGES["/"].title,
  "/desk": "Rules Desk | MTG Rules Desk",
  "/desk/history": "History | MTG Rules Desk",
  "/desk/settings": "Settings | MTG Rules Desk",
  "/about": SEO_PAGES["/about"].title,
  "/patch-history": "Patch History | MTG Rules Desk",
  "/terms": "Terms of Service | MTG Rules Desk",
  "/privacy": SEO_PAGES["/privacy"].title,
}

export function getRouteMetadata(
  route: AppRoute,
  { origin, allowIndexing }: MetadataOptions,
): RouteMetadata {
  const publicIndexable = route === "/" || route === "/about"
  const normalizedOrigin = normalizeSiteOrigin(origin)
  return {
    title: titles[route],
    description: descriptions[route],
    canonical: canonicalUrl(normalizedOrigin, route),
    robots: allowIndexing && publicIndexable ? "index, follow" : "noindex, nofollow",
    image: `${normalizedOrigin}/pwa-512x512.png`,
    structuredData: createPageStructuredData(route, normalizedOrigin),
  }
}

function ensureMeta(name: string): HTMLMetaElement {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!element) {
    element = document.createElement("meta")
    element.name = name
    document.head.append(element)
  }
  return element
}

function ensurePropertyMeta(property: string): HTMLMetaElement {
  let element = document.head.querySelector<HTMLMetaElement>(
    `meta[property="${property}"]`,
  )
  if (!element) {
    element = document.createElement("meta")
    element.setAttribute("property", property)
    document.head.append(element)
  }
  return element
}

export function applyRouteMetadata(metadata: RouteMetadata): void {
  document.title = metadata.title
  ensureMeta("description").content = metadata.description
  ensureMeta("robots").content = metadata.robots
  ensureMeta("application-name").content = "MTG Rules Desk"
  ensureMeta("twitter:card").content = "summary"
  ensureMeta("twitter:title").content = metadata.title
  ensureMeta("twitter:description").content = metadata.description
  ensureMeta("twitter:image").content = metadata.image
  ensureMeta("twitter:image:alt").content = "MTG Rules Desk application icon"
  ensurePropertyMeta("og:type").content = "website"
  ensurePropertyMeta("og:site_name").content = "MTG Rules Desk"
  ensurePropertyMeta("og:locale").content = "en_US"
  ensurePropertyMeta("og:title").content = metadata.title
  ensurePropertyMeta("og:description").content = metadata.description
  ensurePropertyMeta("og:url").content = metadata.canonical
  ensurePropertyMeta("og:image").content = metadata.image
  ensurePropertyMeta("og:image:alt").content = "MTG Rules Desk application icon"

  let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!canonical) {
    canonical = document.createElement("link")
    canonical.rel = "canonical"
    document.head.append(canonical)
  }
  canonical.href = metadata.canonical

  const existingStructuredData = document.head.querySelector<HTMLScriptElement>(
    'script[type="application/ld+json"][data-route-seo]',
  )
  if (!metadata.structuredData) {
    existingStructuredData?.remove()
    return
  }
  const structuredData = existingStructuredData ?? document.createElement("script")
  structuredData.type = "application/ld+json"
  structuredData.dataset.routeSeo = ""
  structuredData.textContent = JSON.stringify(metadata.structuredData)
  if (!existingStructuredData) document.head.append(structuredData)
}
