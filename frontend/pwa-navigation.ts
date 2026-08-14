// Firebase Hosting reserves /__ for its OAuth helpers and runtime metadata.
// The app shell must never intercept these same-origin requests.
export const NAVIGATION_FALLBACK_DENYLIST = [/^\/__/]
