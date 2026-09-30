import { useRef, useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, ErrorState, NotAvailable, StatusBadge } from '../components/common/Card'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import type { IngestResponse } from '../lib/types'

type Outcome = { kind: 'done'; data: IngestResponse } | { kind: 'error'; message: string }

export function Ingest() {
  const capabilities = useApi(() => api.capabilities(), [])
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState(false)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [url, setUrl] = useState('')
  const [urlKind, setUrlKind] = useState('github')
  const inputRef = useRef<HTMLInputElement>(null)

  async function upload(file: File) {
    setPending(true)
    setOutcome(null)
    try {
      const form = new FormData()
      form.append('file', file)
      setOutcome({ kind: 'done', data: await api.ingest(form) })
    } catch (cause) {
      setOutcome({
        kind: 'error',
        message: cause instanceof ApiError ? cause.message : String(cause),
      })
    } finally {
      setPending(false)
    }
  }

  async function submitUrl(event: React.FormEvent) {
    event.preventDefault()
    if (!url.trim() || pending) return
    setPending(true)
    setOutcome(null)
    try {
      const form = new FormData()
      form.append('url', url.trim())
      const kind = capabilities.data?.url_inputs?.find((input) => input.kind === urlKind)
      if (kind) form.append('source_type', kind.source_type)
      setOutcome({ kind: 'done', data: await api.ingest(form) })
      setUrl('')
    } catch (cause) {
      setOutcome({
        kind: 'error',
        message: cause instanceof ApiError ? cause.message : String(cause),
      })
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Add Knowledge"
        subtitle="Give PAM something new to remember."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader
            title="Upload a file"
            subtitle="PAM detects the source type from the file itself"
          />
          <div className="p-5">
            <div
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                const file = event.dataTransfer.files?.[0]
                if (file) void upload(file)
              }}
              className={`flex flex-col items-center gap-3 rounded-card border-2 border-dashed px-6 py-10 text-center transition-colors ${
                dragging ? 'border-accent bg-accent-dim/40' : 'border-border'
              }`}
            >
              <p className="text-sm text-text-muted">Drop files here</p>
              <p className="text-xs text-text-faint">or</p>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={pending}
                className="rounded-md border border-border-strong bg-elevated px-4 py-2 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-40"
              >
                Browse Files
              </button>
              <input
                ref={inputRef}
                type="file"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) void upload(file)
                  event.target.value = ''
                }}
              />
            </div>
          </div>
        </Card>

        <AsyncBoundary state={capabilities}>
          {(data) =>
            data.available && (data.url_inputs?.length ?? 0) > 0 ? (
              <Card>
                <CardHeader title="Ingest from a URL" />
                <form onSubmit={submitUrl} className="flex flex-wrap items-end gap-3 p-5">
                  <label className="flex flex-col gap-1.5 text-[11px] text-text-faint">
                    Source
                    <select
                      value={urlKind}
                      onChange={(event) => setUrlKind(event.target.value)}
                      className="rounded-md border border-border bg-elevated px-2.5 py-2 text-xs text-text focus:outline-none"
                    >
                      {data.url_inputs?.map((input) => (
                        <option key={input.kind} value={input.kind}>
                          {input.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex min-w-64 flex-1 flex-col gap-1.5 text-[11px] text-text-faint">
                    URL
                    <input
                      type="url"
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                      placeholder="https://github.com/…"
                      className="rounded-md border border-border bg-elevated px-2.5 py-2 text-[13px] text-text placeholder:text-text-faint focus:outline-none"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={pending || url.trim().length === 0}
                    className="rounded-md bg-accent px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-accent-soft disabled:opacity-40"
                  >
                    Ingest
                  </button>
                </form>
              </Card>
            ) : null
          }
        </AsyncBoundary>

        {pending ? (
          <Card>
            <div
              role="status"
              aria-live="polite"
              className="flex items-center gap-3 px-5 py-6 text-sm text-text-muted"
            >
              {/* PAM's ingestion workflow is synchronous and reports no
                  progress, so this is intentionally indeterminate. */}
              <span
                aria-hidden="true"
                className="size-3.5 animate-spin rounded-full border-2 border-border-strong border-t-accent"
              />
              Ingesting, embedding and indexing. This can take a while for large documents.
            </div>
          </Card>
        ) : null}

        {outcome?.kind === 'error' ? (
          <Card className="border-danger/30">
            <ErrorState message={outcome.message} />
          </Card>
        ) : null}

        {outcome?.kind === 'done' ? (
          <Card>
            <CardHeader
              title="Ingestion result"
              action={
                <StatusBadge
                  status={outcome.data.status === 'processed' ? 'ready' : 'disabled'}
                  label={outcome.data.status}
                  size="sm"
                />
              }
            />
            <dl className="divide-y divide-border text-[13px]">
              {outcome.data.message ? (
                <div className="px-5 py-3 text-text-muted">{outcome.data.message}</div>
              ) : null}
              {(
                [
                  ['Source', outcome.data.source],
                  ['Source type', outcome.data.source_type],
                  ['Note', outcome.data.note_title],
                  ['Note path', outcome.data.note_path],
                  ['Chunks indexed', outcome.data.chunks_stored?.toString()],
                  ['Embedded', outcome.data.embedding_succeeded?.toString()],
                  ['Indexed', outcome.data.indexing_succeeded?.toString()],
                ] as [string, string | undefined][]
              ).map(([label, value]) =>
                value ? (
                  <div key={label} className="flex items-start justify-between gap-4 px-5 py-2.5">
                    <dt className="shrink-0 text-text-muted">{label}</dt>
                    <dd className="min-w-0 truncate text-right font-mono text-xs text-text" title={value}>
                      {value}
                    </dd>
                  </div>
                ) : null,
              )}
            </dl>
            {outcome.data.graph_warning ? (
              <p className="border-t border-border px-5 py-3 text-[13px] text-warning">
                {outcome.data.graph_warning}
              </p>
            ) : null}
          </Card>
        ) : null}

        <Card>
          <CardHeader
            title="Supported source types"
            subtitle="From PAM's live ingestor registry"
          />
          <AsyncBoundary state={capabilities}>
            {(data) =>
              data.available ? (
                <div className="px-5 py-4">
                  <p className="mb-3 font-mono text-[11px] text-text-faint">
                    {data.extension_count} file extensions
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {data.extensions?.map((extension) => (
                      <span
                        key={extension}
                        className="rounded border border-border bg-elevated px-1.5 py-0.5 font-mono text-[11px] text-text-muted"
                      >
                        {extension}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="px-5 py-4 text-[13px]">
                  <NotAvailable />
                </p>
              )
            }
          </AsyncBoundary>
        </Card>
      </div>
    </>
  )
}
