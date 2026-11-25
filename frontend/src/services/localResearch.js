import { isLocalResearchContext } from './experimentalContract.mjs'
import { demoMode } from './demoMode'

// Local research context (dev server at the exact loopback origin, never in the demo). It gates
// the predictive viewer and other local-only routes; it makes no network request by itself.
export function localResearchEnabled() {
  return !demoMode && isLocalResearchContext({ DEV: import.meta.env.DEV }, window.location.origin)
}
