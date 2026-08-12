import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { VitePWA } from "vite-plugin-pwa"

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "prompt",
      injectRegister: false,
      includeAssets: ["favicon.svg", "apple-touch-icon.svg"],
      manifest: {
        name: "MTG Rules Desk",
        short_name: "Rules Desk",
        description: "A grounded Magic: The Gathering rules reference.",
        lang: "en",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#f4f5f2",
        theme_color: "#102a43",
        icons: [
          { src: "/pwa-192x192.svg", sizes: "192x192", type: "image/svg+xml", purpose: "any" },
          {
            src: "/pwa-512x512.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,woff2}"],
        navigateFallback: "/index.html",
        runtimeCaching: [],
      },
    }),
  ],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      thresholds: { lines: 80, functions: 80, statements: 80, branches: 80 },
      exclude: ["src/main.tsx", "src/test/**", "**/*.d.ts"],
    },
  },
})
