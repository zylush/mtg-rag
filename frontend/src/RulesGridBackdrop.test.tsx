import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { RulesGridBackdrop } from "./RulesGridBackdrop"

describe("RulesGridBackdrop", () => {
  it("renders an inert decorative public grid with an accessible variant hook", () => {
    const { container } = render(<RulesGridBackdrop variant="public" />)
    const backdrop = container.querySelector(".rules-grid-backdrop")

    expect(backdrop).toHaveAttribute("data-variant", "public")
    expect(backdrop).toHaveAttribute("aria-hidden", "true")
    expect(backdrop?.querySelector("svg")).toHaveAttribute("focusable", "false")
    expect(backdrop?.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(backdrop?.querySelector("pattern")).toBeInTheDocument()
  })

  it("keeps desk and custom class hooks available for responsive styling", () => {
    const { container } = render(
      <RulesGridBackdrop className="custom-grid" variant="desk" />,
    )
    const backdrop = container.querySelector(".rules-grid-backdrop")

    expect(backdrop).toHaveClass("custom-grid")
    expect(backdrop).toHaveAttribute("data-variant", "desk")
  })
})
