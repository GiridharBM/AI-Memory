import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { Card, CardHeader, EmptyState } from '../components/common/Card'
import { HitCard } from '../components/retrieval/RetrievalPipeline'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import type { SearchResponse } from '../lib/types'

export function Search() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [sourceType, setSourceType] = useState('')
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sources = useApi(() => api.sources(), [])

  const types = Array.from(
    new Set((sources.data?.sources ?? []).map((source) => source.type).filter(Boolean)),
  ) as string[]

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || pending) return

    setPending(true)
    setError(null)
    try {
      setResult(
        await api.search({
          query: trimmed,
          top_k: topK,
          source_type: sourceType || null,
        }),
      )
    } catch (cause) {
      setResult(null)
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Search"
        subtitle="Find relevant memory without generating an answer."
      />

      <form onSubmit={submit} className="mb-6">
        <Card className="p-2 focus-within:border-accent/50">
          <label htmlFor="search-input" className="sr-only">
            Search your memory
          </label>
          <input
            id="search-input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search your memory…"
            className="w-full bg-transparent px-3 py-2.5 text-sm text-text placeholder:text-text-faint focus:outline-none"
          />
          <div className="flex flex-wrap items-end gap-3 border-t border-border px-2 pt-2.5 pb-1">
            <label className="flex flex-col gap-1 text-[11px] text-text-faint">
              Top-K
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value) || 1)}
                className="w-16 rounded-md border border-border bg-elevated px-2 py-1 font-mono text-xs text-text focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px] text-text-faint">
              Type
              <select
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
                className="rounded-md border border-border bg-elevated px-2 py-1 text-xs text-text focus:outline-none"
              >
                <option value="">All types</option>
                {types.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={pending || query.trim().length === 0}
              className="ml-auto shrink-0 rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {pending ? 'Searching…' : 'Search'}
            </button>
          </div>
        </Card>
      </form>

      {error ? (
        <Card className="border-danger/30">
          <p role="alert" className="px-5 py-4 text-[13px] text-danger">
            {error}
          </p>
        </Card>
      ) : null}

      {pending ? (
        <Card>
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-3 px-5 py-8 text-sm text-text-muted"
          >
            <span
              aria-hidden="true"
              className="size-3.5 animate-spin rounded-full border-2 border-border-strong border-t-accent"
            />
            Running hybrid retrieval…
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card>
          <CardHeader
            title="Results"
            subtitle={`${result.count} chunk${result.count === 1 ? '' : 's'} · hybrid dense + BM25 fused with RRF · ${result.latency_seconds !== null ? `completed in ${result.latency_seconds.toFixed(2)}s` : 'latency unavailable'}`}
          />
          {result.results.length === 0 ? (
            <EmptyState
              title="No matching memory"
              hint="No chunk scored above the retrieval floor for this query. Try different terms, or ask PAM a question instead."
            />
          ) : (
            <div className="space-y-3 px-5 py-4">
              {result.results.map((hit) => (
                <HitCard key={hit.entry_id} hit={hit} />
              ))}
            </div>
          )}
        </Card>
      ) : null}

      {!result && !pending && !error ? (
        <Card>
          <EmptyState
            title="Search your memory"
            hint="Retrieval only: returns ranked chunks with real RRF, semantic and BM25 scores. No answer is generated."
          />
        </Card>
      ) : null}
    </>
  )
}
