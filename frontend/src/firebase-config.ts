type FirebaseEnvironment = Readonly<{
  VITE_FIREBASE_API_KEY: string
  VITE_FIREBASE_AUTH_DOMAIN: string
  VITE_FIREBASE_PROJECT_ID: string
  VITE_FIREBASE_APP_ID: string
}>

function required(value: string, name: string): string {
  const normalized = value.trim()
  if (!normalized) throw new Error(`${name} is required`)
  return normalized
}

export function createFirebaseConfig(
  environment: FirebaseEnvironment,
  appHostname: string,
) {
  const projectId = required(
    environment.VITE_FIREBASE_PROJECT_ID,
    "VITE_FIREBASE_PROJECT_ID",
  )
  const configuredAuthDomain = required(
    environment.VITE_FIREBASE_AUTH_DOMAIN,
    "VITE_FIREBASE_AUTH_DOMAIN",
  )
  const firebaseHostingDomain = `${projectId}.web.app`

  return {
    apiKey: required(environment.VITE_FIREBASE_API_KEY, "VITE_FIREBASE_API_KEY"),
    authDomain:
      appHostname.toLowerCase() === firebaseHostingDomain.toLowerCase()
        ? firebaseHostingDomain
        : configuredAuthDomain,
    projectId,
    appId: required(environment.VITE_FIREBASE_APP_ID, "VITE_FIREBASE_APP_ID"),
  }
}
