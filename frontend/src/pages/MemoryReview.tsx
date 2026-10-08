import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import {
  AsyncBoundary,
  Card,
  CardHeader,
  EmptyState,
  StatusBadge,
} from '../components/common/Card'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import type {
  MemoryCandidate,
  MemoryProvenanceResponse,
  MemoryRecord,
} from '../lib/types'

type Tab = 'review' | 'memories'
type StatusFilter = 'pending' | 'all' | 'approved' | 'rejected' | 'superseded'

const STATUS_FILTERS: StatusFilter[] = ['pending', 'all', 'approved', 'rejected', 'superseded']

export function MemoryReview() {
  const [tab, setTab] = useState<Tab>('review')

  return (
    <>
      <PageHeader
        title="Memory Review"
        subtitle="Approve what PAM should durably remember. Nothing is stored without your decision."
      />

      <div className="mb-5 flex gap-2">
        {(
          [
            ['review', 'Review queue'],
            ['memories', 'Memories'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            aria-pressed={tab === value}
            className={`rounded-md border px-3.5 py-2 text-[13px] font-medium transition-colors ${
              tab === value
                ? 'border-accent bg-accent-dim text-accent-soft'
                : 'border-border text-text-muted hover:border-accent/50 hover:text-text'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'review' ? <ReviewQueue /> : <MemoryList />}
    </>
  )
}

function ReviewQueue() {
  const [filter, setFilter] = useState<StatusFilter>('pending')
  const list = useApi(() => api.listCandidates(100, 0), [])

  const visible =
    filter === 'all'
      ? (list.data?.candidates ?? [])
      : (list.data?.candidates ?? []).filter((item) => item.status === filter)

  return (
    <Card>
      <CardHeader
        title="Candidates"
        subtitle="Why PAM wants to remember each item is shown before you decide"
        action={
          <select
            aria-label="Filter by status"
            value={filter}
            onChange={(event) => setFilter(event.target.value as StatusFilter)}
            className="rounded-md border border-border bg-bg px-2.5 py-1.5 text-[13px] text-text focus:border-accent focus:outline-none"
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        }
      />
      <div className="px-5 py-5">
        <AsyncBoundary state={list}>
          {() =>
            visible.length === 0 ? (
              <EmptyState
                title={filter === 'pending' ? 'Nothing awaiting review.' : 'No candidates.'}
                hint="Extract memories from a conversation to fill this queue."
              />
            ) : (
              <ul className="space-y-4">
                {visible.map((item) => (
                  <CandidateCard
                    key={item.id}
                    item={item}
                    onChanged={() => list.reload()}
                  />
                ))}
              </ul>
            )
          }
        </AsyncBoundary>
      </div>
    </Card>
  )
}

function CandidateCard({
  item,
  onChanged,
}: {
  item: MemoryCandidate
  onChanged: () => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.edited_text ?? item.text)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const pending = item.status === 'pending'

  async function run(key: string, work: () => Promise<unknown>) {
    if (busy !== null) return
    setBusy(key)
    setError(null)
    try {
      await work()
      onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  const approve = (edited: boolean) =>
    run('approve', () =>
      api.approveCandidate(item.id, edited && draft.trim() !== item.text ? { edited_text: draft.trim() } : {}),
    )

  return (
    <li
      className={`border-l-2 pl-4 ${
        pending ? 'border-accent' : 'border-border opacity-80'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge
          status={item.status === 'pending' ? 'ready' : 'disabled'}
          label={item.status}
          size="sm"
        />
        <span className="font-mono text-[11px] text-text-muted">
          {item.category}
        </span>
        <span className="font-mono text-[11px] text-text-faint">
          confidence {item.confidence.toFixed(2)}
        </span>
      </div>

      {editing ? (
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          maxLength={2000}
          aria-label="Edit candidate text"
          className="mt-2.5 w-full rounded-md border border-border bg-bg px-3 py-2 text-[13px] text-text focus:border-accent focus:outline-none"
        />
      ) : (
        <p className="mt-1.5 font-display text-[17px] leading-snug text-text">
          {item.edited_text ?? item.text}
        </p>
      )}
      {item.edited_text && !editing ? (
        <p className="mt-1 font-mono text-[11px] text-text-faint">
          Edited before approval. Original: {item.text}
        </p>
      ) : null}

      <div className="mt-2.5 rounded-md bg-elevated/40 px-3 py-2.5">
        <p className="text-[12px] font-medium text-text-muted">
          Why this memory · user message {item.seq}
        </p>
        <p className="mt-1 font-display text-[15px] leading-snug text-text italic">
          “{item.grounding.quoted_text}”
        </p>
        <p className="mt-1 truncate font-mono text-[11px] text-text-faint">
          {item.conversation_id} · {item.message_id}
        </p>
        {item.evidence && item.evidence.citations.length > 0 ? (
          <ul className="mt-1.5 space-y-0.5">
            {item.evidence.citations.map((citation) => (
              <li
                key={`${citation.number}-${citation.source}`}
                className="font-mono text-[11px] text-text-faint"
              >
                [{citation.number}] {citation.source}
                {citation.chunk_id ? ` · ${citation.chunk_id}` : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 font-mono text-[11px] text-text-faint">
            No retrieved-evidence citations.
          </p>
        )}
      </div>

      {item.review ? (
        <p className="mt-2 font-mono text-[11px] text-text-faint">
          {item.review.decision}
          {item.review.reason ? ` · ${item.review.reason}` : null}
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {error}
        </p>
      ) : null}

      {pending ? (
        <div className="mt-3 space-y-2.5">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => approve(editing)}
              className="rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-soft disabled:opacity-50"
            >
              {busy === 'approve' ? 'Approving…' : editing ? 'Approve with edits' : 'Approve'}
            </button>
            {editing ? (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => run('edit', () => api.editCandidate(item.id, { edited_text: draft.trim() }))}
                className="rounded-md border border-border-strong bg-elevated px-3.5 py-1.5 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
              >
                {busy === 'edit' ? 'Saving…' : 'Save edit'}
              </button>
            ) : (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => {
                  setDraft(item.edited_text ?? item.text)
                  setEditing(true)
                }}
                className="rounded-md border border-border-strong bg-elevated px-3.5 py-1.5 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
              >
                Edit
              </button>
            )}
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setRejecting((value) => !value)}
              className="rounded-md border border-border-strong bg-elevated px-3.5 py-1.5 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
            >
              Reject
            </button>
          </div>
          {rejecting ? (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (reason.trim()) {
                  void run('reject', () => api.rejectCandidate(item.id, { reason: reason.trim() }))
                }
              }}
              className="flex gap-2.5"
            >
              <input
                type="text"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Rejection reason (required)…"
                aria-label="Rejection reason"
                className="min-w-0 flex-1 rounded-md border border-border bg-bg px-3 py-2 text-[13px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy !== null || reason.trim().length === 0}
                className="shrink-0 rounded-md border border-danger/40 bg-danger/10 px-3.5 py-2 text-[13px] font-medium text-danger transition-colors hover:border-danger disabled:opacity-50"
              >
                {busy === 'reject' ? 'Rejecting…' : 'Confirm reject'}
              </button>
            </form>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

function MemoryList() {
  const [selectedLogicalId, setSelectedLogicalId] = useState<string | null>(null)
  const list = useApi(() => api.listMemories(100, 0), [])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Memories" subtitle="Durable approved records, newest approval last" />
        <div className="px-5 py-5">
          <AsyncBoundary state={list}>
            {(data) =>
              data.memories.length === 0 ? (
                <EmptyState
                  title="No memories yet."
                  hint="Approve a candidate to store the first one."
                />
              ) : (
                <ul className="divide-y divide-border rounded-md border border-border">
                  {data.memories.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedLogicalId(item.logical_id)}
                        aria-pressed={selectedLogicalId === item.logical_id}
                        className={`flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-elevated/50 ${
                          selectedLogicalId === item.logical_id ? 'bg-elevated/50' : ''
                        }`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-text">
                            {item.text}
                          </span>
                          <span className="mt-0.5 block font-mono text-[11px] text-text-faint">
                            v{item.version} · {item.category}
                          </span>
                        </span>
                        <StatusBadge
                          status={item.status === 'active' ? 'ready' : 'disabled'}
                          label={item.status}
                          size="sm"
                        />
                      </button>
                    </li>
                  ))}
                </ul>
              )
            }
          </AsyncBoundary>
        </div>
      </Card>

      {selectedLogicalId !== null ? (
        <MemoryDetail
          key={selectedLogicalId}
          logicalId={selectedLogicalId}
          onChanged={() => list.reload()}
        />
      ) : null}
    </div>
  )
}

function MemoryDetail({
  logicalId,
  onChanged,
}: {
  logicalId: string
  onChanged: () => void
}) {
  const versions = useApi(() => api.listMemories(100, 0, logicalId), [logicalId])
  const [provenance, setProvenance] = useState<MemoryProvenanceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [supersedeText, setSupersedeText] = useState('')
  const [superseding, setSuperseding] = useState(false)

  const rows = versions.data?.memories ?? []
  const active = rows.find((item) => item.status === 'active') ?? rows[rows.length - 1]

  async function loadProvenance(id: string) {
    setError(null)
    try {
      setProvenance(await api.memoryProvenance(id))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    }
  }

  async function supersede(event: React.FormEvent) {
    event.preventDefault()
    if (!active || superseding || !supersedeText.trim()) return
    setSuperseding(true)
    setError(null)
    try {
      await api.supersedeMemory(active.logical_id, {
        text: supersedeText.trim(),
        category: active.category,
        confidence: active.confidence_at_approval,
      })
      setSupersedeText('')
      versions.reload()
      onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setSuperseding(false)
    }
  }

  return (
    <Card>
      <CardHeader title="Versions & provenance" subtitle={logicalId} />
      <div className="space-y-4 px-5 py-5">
        <AsyncBoundary state={versions}>
          {() => (
            <ul className="space-y-3">
              {rows.map((item: MemoryRecord) => (
                <li key={item.id} className="rounded-md border border-border px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      status={item.status === 'active' ? 'ready' : 'disabled'}
                      label={`v${item.version} · ${item.status}`}
                      size="sm"
                    />
                    <span className="font-mono text-[11px] text-text-faint">
                      {item.category} · confidence {item.confidence_at_approval.toFixed(2)}
                    </span>
                    <button
                      type="button"
                      onClick={() => loadProvenance(item.id)}
                      className="ml-auto text-[12px] text-text-muted underline-offset-2 hover:text-text hover:underline"
                    >
                      Provenance
                    </button>
                  </div>
                  <p className="mt-1.5 text-[13px] text-text">{item.text}</p>
                </li>
              ))}
            </ul>
          )}
        </AsyncBoundary>

        {provenance !== null ? (
          <ProvenanceView record={provenance} />
        ) : null}

        {error ? (
          <p role="alert" className="text-[13px] text-danger">
            {error}
          </p>
        ) : null}

        {active && active.status === 'active' ? (
          <form onSubmit={supersede} className="flex gap-2.5">
            <input
              type="text"
              value={supersedeText}
              onChange={(event) => setSupersedeText(event.target.value)}
              placeholder="New version text…"
              aria-label="New version text"
              className="min-w-0 flex-1 rounded-md border border-border bg-bg px-3 py-2 text-[13px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
            />
            <button
              type="submit"
              disabled={superseding || supersedeText.trim().length === 0}
              className="shrink-0 rounded-md border border-border-strong bg-elevated px-3.5 py-2 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
            >
              {superseding ? 'Saving…' : 'New version'}
            </button>
          </form>
        ) : null}
      </div>
    </Card>
  )
}

function ProvenanceView({ record }: { record: MemoryProvenanceResponse }) {
  const { source, conversation } = record
  return (
    <div className="rounded-md bg-elevated/40 px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-text-faint">
        Provenance
      </p>
      <p className="mt-1.5 text-[13px] text-text-muted italic">
        “{source.quoted_text || 'No grounding quote recorded.'}”
      </p>
      <p className="mt-1 font-mono text-[11px] text-text-faint">
        message {source.seq} · {source.message_id}
      </p>
      <p className="mt-0.5 font-mono text-[11px] text-text-faint">
        conversation{' '}
        {conversation ? `${conversation.title} (${conversation.id})` : source.conversation_id}
      </p>
      {source.evidence?.citations && source.evidence.citations.length > 0 ? (
        <ul className="mt-1.5 space-y-0.5">
          {source.evidence.citations.map((citation) => (
            <li
              key={`${citation.number}-${citation.source}`}
              className="font-mono text-[11px] text-text-faint"
            >
              [{citation.number}] {citation.source}
              {citation.chunk_id ? ` · ${citation.chunk_id}` : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 font-mono text-[11px] text-text-faint">
          No retrieved-evidence citations.
        </p>
      )}
    </div>
  )
}
