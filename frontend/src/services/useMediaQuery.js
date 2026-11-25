import { useEffect, useState } from 'react'

// Narrow layouts that change what is rendered (not only CSS): true while the media query matches.
export const NARROW_SCREEN = '(max-width: 700px)'
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const list = window.matchMedia(query), change = () => setMatches(list.matches)
    change(); list.addEventListener('change', change)
    return () => list.removeEventListener('change', change)
  }, [query])
  return matches
}
