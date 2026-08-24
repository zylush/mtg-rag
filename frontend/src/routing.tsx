/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

export type AppRoute =
  | "/"
  | "/desk"
  | "/desk/history"
  | "/desk/settings"
  | "/about"
  | "/patch-history"
  | "/terms"
  | "/privacy"

export function normalizeRoute(pathname: string): AppRoute {
  if (pathname === "/auth" || pathname === "/login") return "/"
  if (
    pathname === "/desk" ||
    pathname === "/desk/history" ||
    pathname === "/desk/settings" ||
    pathname === "/about" ||
    pathname === "/patch-history" ||
    pathname === "/terms" ||
    pathname === "/privacy"
  ) {
    return pathname
  }
  if (pathname === "/e2e.html") return "/desk"
  return "/"
}

interface RouterContextValue {
  route: AppRoute
  navigate(to: AppRoute, options?: { replace?: boolean }): void
}

const RouterContext = createContext<RouterContextValue | null>(null)

export function RouterProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<AppRoute>(() => normalizeRoute(window.location.pathname))

  useEffect(() => {
    const normalized = normalizeRoute(window.location.pathname)
    if (window.location.pathname !== normalized) {
      window.history.replaceState({}, "", normalized)
    }
    const handlePopState = () => setRoute(normalizeRoute(window.location.pathname))
    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [])

  const navigate = useCallback((to: AppRoute, options?: { replace?: boolean }) => {
    if (window.location.pathname !== to) {
      const method = options?.replace ? "replaceState" : "pushState"
      window.history[method]({}, "", to)
    }
    setRoute(to)
  }, [])

  const value = useMemo(() => ({ route, navigate }), [navigate, route])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterContextValue {
  const context = useContext(RouterContext)
  if (!context) throw new Error("useRouter must be used inside RouterProvider")
  return context
}

type AppLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "onClick"> & {
  to: AppRoute
}

export function AppLink({ to, children, ...props }: AppLinkProps) {
  const { route, navigate } = useRouter()

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return
    }
    event.preventDefault()
    navigate(to)
  }

  return (
    <a {...props} href={to} aria-current={route === to ? "page" : undefined} onClick={handleClick}>
      {children}
    </a>
  )
}
