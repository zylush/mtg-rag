import type { AppRoute } from "./routing"

export interface RouteMetadata {
  title: string
  description: string
  canonical: string
  robots: "index, follow" | "noindex, nofollow"
}

interface MetadataOptions {
  origin: string
  allowIndexing: boolean
}

const descriptions: Record<AppRoute, string> = {
  "/": "Citation-first Magic: The Gathering answers grounded in the Comprehensive Rules, current Oracle text, and attributed card rulings.",
  "/login": "Sign in to MTG Rules Desk to ask grounded Magic: The Gathering rules questions.",
  "/desk": "Ask a grounded Magic: The Gathering rules question and review its citations.",
  "/desk/history": "Review saved MTG Rules Desk conversations.",
  "/desk/settings": "Manage MTG Rules Desk product links, installation, and account controls.",
  "/about": "Learn how MTG Rules Desk retrieves rules, Oracle text, and rulings to produce citation-first Magic answers.",
  "/terms": "Draft Terms of Service outline for MTG Rules Desk, pending legal review.",
  "/privacy": "Draft Privacy Policy outline for MTG Rules Desk, pending legal review.",
}

const titles: Record<AppRoute, string> = {
  "/": "MTG Rules Desk | Citation-First Magic Rules Answers",
  "/login": "Sign in | MTG Rules Desk",
  "/desk": "Rules Desk | MTG Rules Desk",
  "/desk/history": "History | MTG Rules Desk",
  "/desk/settings": "Settings | MTG Rules Desk",
  "/about": "How MTG Rules Desk Works",
  "/terms": "Draft Terms of Service | MTG Rules Desk",
  "/privacy": "Draft Privacy Policy | MTG Rules Desk",
}

export function getRouteMetadata(
  route: AppRoute,
  { origin, allowIndexing }: MetadataOptions,
): RouteMetadata {
  const publicIndexable = route === "/" || route === "/about"
  return {
    title: titles[route],
    description: descriptions[route],
    canonical: `${origin}${route}`,
    robots: allowIndexing && publicIndexable ? "index, follow" : "noindex, nofollow",
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

export function applyRouteMetadata(metadata: RouteMetadata): void {
  document.title = metadata.title
  ensureMeta("description").content = metadata.description
  ensureMeta("robots").content = metadata.robots

  let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!canonical) {
    canonical = document.createElement("link")
    canonical.rel = "canonical"
    document.head.append(canonical)
  }
  canonical.href = metadata.canonical
}
