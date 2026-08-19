import path from "node:path"
import { fileURLToPath } from "node:url"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { loadEnv, type HtmlTagDescriptor, type Plugin } from "vite"
import { VitePWA } from "vite-plugin-pwa"
import { defineConfig } from "vitest/config"

import { NAVIGATION_FALLBACK_DENYLIST } from "./pwa-navigation.ts"
import {
  DEFAULT_PUBLIC_SITE_ORIGIN,
  SEO_PAGES,
  canonicalUrl,
  createPageStructuredData,
  createRobotsTxt,
  createSitemapXml,
  normalizeSiteOrigin,
  type SeoShellRoute,
} from "./seo-config.ts"

const frontendRoot = fileURLToPath(new URL(".", import.meta.url))

const routeByHtmlPath: Record<string, SeoShellRoute> = {
  "/": "/",
  "/index.html": "/",
  "/about.html": "/about",
  "/terms.html": "/terms",
  "/privacy.html": "/privacy",
}

function seoPlugin({
  origin,
  allowIndexing,
}: {
  origin: string
  allowIndexing: boolean
}): Plugin {
  const robots = createRobotsTxt({ origin, allowIndexing })
  const sitemap = createSitemapXml(origin)

  return {
    name: "mtg-rules-desk-seo",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = request.url?.split("?", 1)[0]
        const content = pathname === "/robots.txt" ? robots : pathname === "/sitemap.xml" ? sitemap : null
        if (content === null) {
          next()
          return
        }
        response.statusCode = 200
        response.setHeader(
          "Content-Type",
          pathname === "/robots.txt"
            ? "text/plain; charset=utf-8"
            : "application/xml; charset=utf-8",
        )
        response.end(content)
      })
    },
    transformIndexHtml: {
      order: "post",
      handler(html, context) {
        const route = routeByHtmlPath[context.path] ?? "/"
        const page = SEO_PAGES[route]
        const canonical = canonicalUrl(origin, route)
        const image = `${origin}/pwa-512x512.png`
        const robotsContent =
          allowIndexing && page.indexable ? "index, follow" : "noindex, nofollow"
        const tags: HtmlTagDescriptor[] = [
          { tag: "title", children: page.title, injectTo: "head" },
          {
            tag: "meta",
            attrs: { name: "description", content: page.description },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "robots", content: robotsContent },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "application-name", content: "MTG Rules Desk" },
            injectTo: "head",
          },
          {
            tag: "link",
            attrs: { rel: "canonical", href: canonical },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:type", content: "website" },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:site_name", content: "MTG Rules Desk" },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:locale", content: "en_US" },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:title", content: page.title },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:description", content: page.description },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:url", content: canonical },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { property: "og:image", content: image },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: {
              property: "og:image:alt",
              content: "MTG Rules Desk application icon",
            },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "twitter:card", content: "summary" },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "twitter:title", content: page.title },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "twitter:description", content: page.description },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: { name: "twitter:image", content: image },
            injectTo: "head",
          },
          {
            tag: "meta",
            attrs: {
              name: "twitter:image:alt",
              content: "MTG Rules Desk application icon",
            },
            injectTo: "head",
          },
        ]
        const structuredData = createPageStructuredData(route, origin)
        if (structuredData) {
          tags.push({
            tag: "script",
            attrs: { type: "application/ld+json", "data-route-seo": "" },
            children: JSON.stringify(structuredData),
            injectTo: "head",
          })
        }
        return { html, tags }
      },
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "robots.txt", source: robots })
      this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemap })
    },
  }
}

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, frontendRoot, "")
  const origin = normalizeSiteOrigin(
    environment.VITE_PUBLIC_SITE_URL || DEFAULT_PUBLIC_SITE_ORIGIN,
  )
  const allowIndexing = environment.VITE_ALLOW_INDEXING === "true"

  return {
    plugins: [
      seoPlugin({ origin, allowIndexing }),
      react(),
      tailwindcss(),
      VitePWA({
      registerType: "autoUpdate",
      injectRegister: false,
      includeAssets: ["favicon.ico", "favicon.svg", "apple-touch-icon-180x180.png"],
      manifest: {
        id: "/",
        name: "MTG Rules Desk",
        short_name: "Rules Desk",
        description: "A grounded Magic: The Gathering rules reference.",
        lang: "en",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#17120f",
        theme_color: "#17120f",
        icons: [
          {
            src: "/pwa-192x192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "/pwa-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "/maskable-icon-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [...NAVIGATION_FALLBACK_DENYLIST],
        runtimeCaching: [],
      },
      }),
    ],
    build: {
      rollupOptions: {
        input: {
          main: path.resolve(frontendRoot, "index.html"),
          about: path.resolve(frontendRoot, "about.html"),
          terms: path.resolve(frontendRoot, "terms.html"),
          privacy: path.resolve(frontendRoot, "privacy.html"),
        },
      },
    },
    test: {
      environment: "jsdom",
      exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
      globals: true,
      setupFiles: "./src/test/setup.ts",
      coverage: {
        provider: "v8",
        reporter: ["text", "json-summary"],
        thresholds: { lines: 80, functions: 80, statements: 80, branches: 80 },
        exclude: ["src/main.tsx", "src/test/**", "**/*.d.ts"],
      },
    },
  }
})
