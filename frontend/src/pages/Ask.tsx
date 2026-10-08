import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { Card, CardHeader, ErrorState, NotAvailable, StatusBadge } from '../components/common/Card'
import { HitCard, RetrievalPipeline } from '../components/retrieval/RetrievalPipeline'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import type { AskResponse } from '../lib/types'

const SUGGESTIONS = [
  'How many sources are indexed?',
  'Which features are enabled?',
  'What file types can PAM ingest?',
  'What is PAM and how does retrieval work?',
]

export function Ask() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showRetrieval, setShowRetrieval] = useState(false)

  const retrieval = useApi(() => api.retrieval(), [])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || pending) return

    setPending(true)
    setError(null)
    try {
      setAnswer(await api.ask({ question: trimmed, top_k: 5 }))
    } catch (cause) {
      setAnswer(null)
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Ask PAM"
        subtitle="Ask questions about the knowledge you've given PAM."
      />

      <form onSubmit={submit} className="mb-6">
        <Card className="p-2 focus-within:border-accent/50">
          <label htmlFor="ask-input" className="sr-only">
            Ask a question about your knowledge
          </label>
          <textarea
            id="ask-input"
            rows={2}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) submit(event)
            }}
            placeholder="Ask something about your memory…"
            className="w-full resize-none bg-transparent px-3 py-2.5 text-sm text-text placeholder:text-text-faint focus:outline-none"
          />
          <div className="flex items-center justify-between gap-3 px-2 pb-1">
            <p className="text-[11px] text-text-faint">
              Answered from retrieved memory. PAM abstains when evidence is insufficient.
            </p>
            <button
              type="submit"
              disabled={pending || question.trim().length === 0}
              className="shrink-0 rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {pending ? 'Thinking…' : 'Ask →'}
            </button>
          </div>
        </Card>
      </form>

      {answer === null && !pending && !error ? (
        <div className="mb-8">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
            Suggested
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setQuestion(suggestion)}
                className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text-muted transition-colors hover:border-accent hover:text-accent-soft"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
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
            Retrieving evidence and generating an answer…
            <span className="text-text-faint">
              The local model runs on your machine, so a cold first answer can take up to a
              minute.
            </span>
          </div>
        </Card>
      ) : null}

      {error ? (
        <Card className="border-danger/30">
          <ErrorState message={error} />
        </Card>
      ) : null}

      {answer ? (
        <div className="space-y-6">
          <section>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
              You
            </p>
            <p className="text-sm text-text">{answer.question}</p>
          </section>

          <Card>
            <CardHeader
              title="PAM"
              subtitle={
                answer.origin === 'system'
                  ? 'Answered from deterministic system facts — no retrieval, no citations'
                  : answer.model
                    ? `Generated by ${answer.model}`
                    : undefined
              }
              action={
                answer.outcome === 'abstained' ? (
                  <StatusBadge status="disabled" label="Abstained" size="sm" />
                ) : (
                  <StatusBadge status="ready" label="Answered" size="sm" />
                )
              }
            />
            <div className="px-5 py-4">
              <p className="text-sm leading-relaxed whitespace-pre-wrap text-text">
                {answer.answer}
              </p>
              {answer.abstention_reason ? (
                <p className="mt-3 border-t border-border pt-3 font-mono text-[11px] text-text-faint">
                  Gate reason: {answer.abstention_reason}
                </p>
              ) : null}
              {answer.latency_seconds !== null ? (
                <p className="mt-2 font-mono text-[11px] text-text-faint">
                  Generated in {answer.latency_seconds.toFixed(2)}s
                </p>
              ) : null}
              {answer.invalid_citations.length > 0 ? (
                <p className="mt-2 font-mono text-[11px] text-warning">
                  Cited source numbers outside the retrieved context:{' '}
                  {answer.invalid_citations.join(', ')}
                </p>
              ) : null}
            </div>
          </Card>

          {answer.origin === 'retrieval' ? (
            <section>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
                Sources
              </p>
              {answer.sources.length === 0 ? (
                <Card>
                  <p className="px-5 py-6 text-[13px]">
                    <NotAvailable />
                  </p>
                </Card>
              ) : (
                <div className="space-y-3">
                  {answer.sources.map((hit, index) => (
                    <HitCard
                      key={hit.entry_id}
                      hit={hit}
                      citationNumber={index + 1}
                      showScores
                    />
                  ))}
                </div>
              )}
            </section>
          ) : null}

          <Card>
            <button
              type="button"
              onClick={() => setShowRetrieval((value) => !value)}
              aria-expanded={showRetrieval}
              className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
            >
              <span className="text-[13px] font-medium text-text">
                View retrieval details
              </span>
              <span aria-hidden="true" className="text-text-faint">
                {showRetrieval ? '▲' : '▼'}
              </span>
            </button>
            {showRetrieval ? (
              <div className="animate-[fade-in_160ms_ease-out] border-t border-border">
                {retrieval.error ? (
                  <p className="px-5 py-4 text-[13px]">
                    <NotAvailable />
                  </p>
                ) : retrieval.data?.available ? (
                  <RetrievalPipeline config={retrieval.data} detail />
                ) : (
                  <p className="px-5 py-4 text-[13px]">
                    <NotAvailable />
                  </p>
                )}
              </div>
            ) : null}
          </Card>
        </div>
      ) : null}
    </>
  )
}
