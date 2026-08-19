type BrandMarkProps = {
  className?: string
}

export function BrandMark({ className }: BrandMarkProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      data-brand-mark
      focusable="false"
      viewBox="0 0 48 48"
    >
      <rect className="brand-mark-field" x="3" y="3" width="42" height="42" rx="10" />
      <path className="brand-mark-page" d="M11 12h17.5c6.3 0 10.5 3.5 10.5 9 0 4-2.2 7-6.1 8.2L39 37h-8.7l-5.2-7h-5.4v7H11V12Zm8.7 7v5h8.1c1.8 0 3-1 3-2.6 0-1.5-1.2-2.4-3-2.4h-8.1Z" />
      <path className="brand-mark-tab" d="M7 16h4v21h11v4H7V16Z" />
      <path className="brand-mark-rule" d="M20 33h5.1l3 4H20v-4Z" />
    </svg>
  )
}
