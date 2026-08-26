import { useId } from "react"

interface RulesGridBackdropProps {
  className?: string
  variant?: "public" | "desk"
}

/**
 * A quiet, decorative rules-grid texture for the two primary product surfaces.
 * The SVG is intentionally inert so it never competes with content or controls.
 */
export function RulesGridBackdrop({
  className,
  variant = "public",
}: RulesGridBackdropProps) {
  const instanceId = useId().replace(/:/g, "")
  const patternId = `rules-grid-pattern-${variant}-${instanceId}`

  return (
    <div
      aria-hidden="true"
      className={["rules-grid-backdrop", `rules-grid-backdrop-${variant}`, className]
        .filter(Boolean)
        .join(" ")}
      data-variant={variant}
    >
      <svg
        aria-hidden="true"
        className="rules-grid-backdrop-svg"
        focusable="false"
        preserveAspectRatio="none"
        viewBox="0 0 320 180"
      >
        <defs>
          <pattern
            height="32"
            id={patternId}
            patternUnits="userSpaceOnUse"
            width="32"
          >
            <path d="M32 0H0V32" fill="none" />
          </pattern>
        </defs>
        <rect
          className="rules-grid-pattern"
          fill={`url(#${patternId})`}
          height="100%"
          width="100%"
        />
        <path
          className="rules-grid-trace"
          d="M-24 134C38 101 72 101 126 124s93 27 218-40"
          fill="none"
          pathLength="1"
        />
      </svg>
    </div>
  )
}
