import { useCallback, useEffect, useState } from 'react'

/**
 * Minimal hash router.
 *
 * PAM's GUI is a single local page talking to one local process: there is no
 * deep-link sharing, no SSR and no SEO surface, so a dependency-free hash router
 * is the right size. `navigate()` is a normal function so it can be called from
 * event handlers, not just click handlers.
 */
export interface Route {
  path: string
  segments: string[]
}

function parse(hash: string): Route {
  const path = hash.replace(/^#/, '') || '/'
  const normalized = path.startsWith('/') ? path : `/${path}`
  return {
    path: normalized,
    segments: normalized.split('/').filter(Boolean),
  }
}

export function navigate(path: string): void {
  const target = path.startsWith('/') ? path : `/${path}`
  if (window.location.hash === `#${target}`) return
  window.location.hash = target
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))

  const onChange = useCallback(() => setRoute(parse(window.location.hash)), [])

  useEffect(() => {
    window.addEventListener('hashchange', onChange)
    // Normalise an empty hash so the first paint is the dashboard, not a blank.
    if (!window.location.hash) window.location.hash = '/dashboard'
    return () => window.removeEventListener('hashchange', onChange)
  }, [onChange])

  return route
}
