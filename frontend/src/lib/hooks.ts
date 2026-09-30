import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from './api'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/**
 * Run a PAM API call and track loading / empty / error / success.
 *
 * Every data-driven view in the GUI goes through this so the four required
 * states are uniform. A stale response is discarded when `deps` change or the
 * component unmounts, so a slow ingest cannot overwrite a newer view.
 */
export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const generation = useRef(0)

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    const mine = ++generation.current
    setLoading(true)
    setError(null)

    load()
      .then((result) => {
        if (generation.current !== mine) return
        setData(result)
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (generation.current !== mine) return
        setData(null)
        setError(cause instanceof ApiError ? cause.message : String(cause))
        setLoading(false)
      })
    // `load` is intentionally excluded: callers pass inline closures and the
    // `deps` list is the explicit, reviewable dependency set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { data, error, loading, reload }
}

/** Format a byte count for display. Returns null-safe text for unknown sizes. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return 'Not available'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`
}

/** Render a ledger timestamp (ISO, UTC) for display without lying about it. */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Never'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
