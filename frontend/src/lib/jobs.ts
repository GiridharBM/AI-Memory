import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, api } from './api'
import type { GenerationJob } from './types'

const POLL_INTERVAL_MS = 2000

const TERMINAL = new Set(['done', 'failed', 'cancelled'])

export interface JobState {
  job: GenerationJob | null
  loading: boolean
  error: string | null
  cancel: () => void
  cancelling: boolean
}

/**
 * Poll a generation job until it reaches a terminal state.
 *
 * Mirrors the `useApi` contract (loading / error / data) with polling
 * semantics layered on top: the interval stops at DONE/FAILED/CANCELLED
 * and is always cleared on unmount, so no stale update can land.
 */
export function useJob(jobId: string | null): JobState {
  const [job, setJob] = useState<GenerationJob | null>(null)
  const [loading, setLoading] = useState(jobId !== null)
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [tracked, setTracked] = useState(jobId)
  const alive = useRef(true)

  // Reset per-job state during render when the tracked job changes — the
  // React-endorsed alternative to resetting inside the polling effect.
  if (tracked !== jobId) {
    setTracked(jobId)
    setJob(null)
    setError(null)
    setLoading(jobId !== null)
    setCancelling(false)
  }

  useEffect(() => {
    alive.current = true
    if (jobId === null) {
      return () => {
        alive.current = false
      }
    }

    let timer: ReturnType<typeof setInterval> | null = null

    function poll() {
      api
        .getJob(jobId as string)
        .then((current) => {
          if (!alive.current) return
          setJob(current)
          setError(null)
          setLoading(false)
          if (TERMINAL.has(current.status)) {
            if (timer !== null) {
              clearInterval(timer)
              timer = null
            }
          }
        })
        .catch((cause: unknown) => {
          if (!alive.current) return
          setError(cause instanceof ApiError ? cause.message : String(cause))
          setLoading(false)
          if (timer !== null) {
            clearInterval(timer)
            timer = null
          }
        })
    }

    poll()
    timer = setInterval(poll, POLL_INTERVAL_MS)

    return () => {
      alive.current = false
      if (timer !== null) clearInterval(timer)
    }
  }, [jobId])

  const cancel = useCallback(() => {
    if (jobId === null || cancelling) return
    setCancelling(true)
    api
      .cancelJob(jobId)
      .then((updated) => {
        if (!alive.current) return
        setJob(updated)
        setCancelling(false)
      })
      .catch((cause: unknown) => {
        if (!alive.current) return
        setError(cause instanceof ApiError ? cause.message : String(cause))
        setCancelling(false)
      })
  }, [jobId, cancelling])

  return { job, loading, error, cancel, cancelling }
}
