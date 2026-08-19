import { X } from "lucide-react"

export function InstallPromptBanner({
  onDismiss,
  onInstall,
}: {
  onDismiss: () => void
  onInstall: () => void
}) {
  return (
    <aside className="mobile-install-banner" aria-label="Install MTG Rules Desk">
      <div className="install-banner-copy">
        <strong>Keep the rules desk close</strong>
        <span>Install the app shell for quick access. Live answers still need internet.</span>
      </div>
      <div className="install-banner-actions">
        <button className="install-banner-action" type="button" onClick={onInstall}>
          Add to home screen
        </button>
        <button
          aria-label="Dismiss install prompt"
          className="install-banner-dismiss"
          type="button"
          onClick={onDismiss}
        >
          <X aria-hidden="true" size={18} />
        </button>
      </div>
    </aside>
  )
}
