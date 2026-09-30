import { useState } from 'react'

import { NotAvailable, StatusBadge } from '../common/Card'
import type { RetrievalConfig, SearchHit } from '../../lib/types'
import { navigate } from '../../lib/router'

/**
 * Retrieval pipeline visualisation.
 *
 * Renders only the stages the running configuration actually has. A stage whose
 * feature flag is off is drawn explicitly as disabled rather than hidden, so the
 * diagram never implies that reranking or HyDE is active when it is not.
 */
export function RetrievalPipeline({
  config,
  detail = false,
}: {
  config: RetrievalConfig | null
  detail?: boolean
}) {
  if (config === null) {
    return (
      <p className="px-5 py-4 text-[13px]">
        <NotAvailable />
      </p>
    )
  }

  // Retrieval legs run in parallel and are fused; generation is a linear tail.
  const parallel = config.stages.filter((stage) =>
    ['hyde', 'semantic', 'bm25'].includes(stage.id),
  )
  const linear = config.stages.filter((stage) => !['hyde', 'semantic', 'bm25'].includes(stage.id))

  return (
    <div className="px-5 py-4">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
        User query
      </p>
      <StageRow stage={config.stages.find((s) => s.id === 'query_processing')!} />

      <div className="ml-3 border-l border-border pl-4">
        <p className="py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
          Retrieval legs
        </p>
        <ul className="space-y-1.5">
          {parallel.map((stage) => (
            <li key={stage.id}>
              <StageRow stage={stage} />
            </li>
          ))}
        </ul>
      </div>

      <div className="ml-3 border-l border-border pl-4">
        <p className="py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint">
          {detail ? 'Fusion, gating and generation' : 'Fusion and generation'}
        </p>
        <ul className="space-y-1.5">
          {linear.map((stage) => (
            <li key={stage.id}>
              <StageRow stage={stage} />
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-4 font-mono text-[11px] text-text-faint">
        RRF k = {config.rrf_k} · abstention min cosine = {config.min_cosine} · QA timeout ={' '}
        {config.qa_timeout_seconds}s
      </p>
    </div>
  )
}

function StageRow({ stage }: { stage: { id: string; label: string; active: boolean; detail?: string | null } }) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 ${
        stage.active ? 'border-border bg-elevated' : 'border-dashed border-border/70 bg-transparent'
      }`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden="true"
          className={`text-[10px] ${stage.active ? 'text-accent' : 'text-text-faint'}`}
        >
          {stage.active ? '◆' : '◇'}
        </span>
        <span
          className={`truncate text-[13px] ${stage.active ? 'text-text' : 'text-text-faint line-through decoration-border-strong'}`}
        >
          {stage.label}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {stage.detail ? (
          <span className="hidden font-mono text-[11px] text-text-faint sm:inline">
            {stage.detail}
          </span>
        ) : null}
        <StatusBadge status={stage.active ? 'ready' : 'disabled'} size="sm" />
      </span>
    </div>
  )
}

/**
 * One retrieval score.
 *
 * Renders nothing but the label when PAM does not expose the value, so a
 * disabled reranker never appears as a real 0.0 score.
 */
export function ScoreValue({
  label,
  value,
  digits = 4,
  hint,
}: {
  label: string
  value: number | null | undefined
  digits?: number
  hint?: string
}) {
  return (
    <div title={hint}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-faint">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-xs text-text">
        {value === null || value === undefined ? (
          <span className="text-text-faint italic">Not available</span>
        ) : (
          value.toFixed(digits)
        )}
      </p>
    </div>
  )
}

/** A retrieved chunk with its real provenance and per-leg scores. */
export function HitCard({
  hit,
  citationNumber,
  showScores = true,
}: {
  hit: SearchHit
  citationNumber?: number
  showScores?: boolean
}) {
  const [open, setOpen] = useState(false)
  const heading = hit.metadata?.heading ?? hit.metadata?.parent_heading ?? null

  return (
    <article className="rounded-card border border-border bg-surface">
      <div className="flex items-start gap-3 px-4 py-3">
        {citationNumber !== undefined ? (
          <span className="mt-0.5 shrink-0 font-mono text-[11px] text-text-faint">
            {String(citationNumber).padStart(2, '0')}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="w-full text-left"
          >
            <p className="truncate text-[13px] font-medium text-text">{hit.source}</p>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 font-mono text-[11px] text-text-faint">
              {hit.source_type ? <span className="uppercase">{hit.source_type}</span> : null}
              <span>chunk {hit.chunk_index}</span>
              {heading ? <span className="truncate">§ {heading}</span> : null}
            </p>
          </button>

          <p className={`mt-2 text-[13px] leading-relaxed text-text-muted ${open ? '' : 'line-clamp-3'}`}>
            {hit.text}
          </p>

          {showScores ? (
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border pt-3 sm:grid-cols-4">
              <ScoreValue label="RRF" value={hit.score} digits={5} />
              <ScoreValue label="Semantic" value={hit.cosine_score} />
              <ScoreValue label="BM25" value={hit.bm25_score} digits={3} />
              <ScoreValue
                label="Rerank"
                value={hit.rerank_score}
                hint={hit.rerank_score === null ? 'Reranker disabled or did not score this hit' : undefined}
              />
            </div>
          ) : null}

          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              className="text-[11px] font-medium text-accent transition-colors hover:text-accent-soft"
            >
              {open ? 'Hide chunk' : 'Show full chunk'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/search')}
              className="text-[11px] font-medium text-text-muted transition-colors hover:text-text"
            >
              Open source →
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}
