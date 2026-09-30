import { PageHeader } from '../components/dashboard/MetricCard'
import { KnowledgeSources } from '../components/dashboard/KnowledgeSources'
import { AsyncBoundary, Card, CardHeader, EmptyState, StatusBadge } from '../components/common/Card'
import { api } from '../lib/api'
import { formatTimestamp, useApi } from '../lib/hooks'
import { navigate, useRoute } from '../lib/router'

export function Memories() {
  const route = useRoute()
  const detailId = route.segments[1]

  return detailId ? <MemoryDetail id={detailId} /> : <MemoryList />
}

function MemoryList() {
  const state = useApi(() => api.sources(), [])

  return (
    <>
      <PageHeader
        title="Memories"
        subtitle="Everything PAM currently holds, as reported by the vector store."
        action={
          <button
            type="button"
            onClick={() => navigate('/ingest')}
            className="rounded-md border border-accent/40 bg-accent-dim px-3.5 py-2 text-[13px] font-medium text-accent-soft transition-colors hover:border-accent hover:bg-accent/20"
          >
            + Add Knowledge
          </button>
        }
      />

      <AsyncBoundary state={state}>
        {(data) => {
          if (!data.available) {
            return (
              <Card className="border-danger/30">
                <CardHeader title="Memories" />
                <p className="px-5 py-4 text-[13px] text-text-muted">{data.config_error}</p>
              </Card>
            )
          }

          return (
            <div className="space-y-6">
              <KnowledgeSources
                slices={data.by_type.map(([name, chunks]) => ({ name, chunks }))}
                totalChunks={data.total_chunks}
              />

              <Card>
                <CardHeader
                  title="Indexed Sources"
                  subtitle={`${data.total} source${data.total === 1 ? '' : 's'} in the vector store`}
                />
                {data.sources.length === 0 ? (
                  <EmptyState
                    title="Nothing here yet."
                    hint="Ingest a document to give PAM something to remember."
                  />
                ) : (
                  <ul className="divide-y divide-border">
                    {data.sources.map((source) => (
                      <li key={source.id}>
                        <button
                          type="button"
                          onClick={() => navigate(`/memories/${source.id}`)}
                          className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors hover:bg-elevated/50"
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-text">
                              {source.name}
                            </span>
                            <span className="mt-0.5 block truncate font-mono text-[11px] text-text-faint">
                              {source.source}
                            </span>
                          </span>
                          <span className="shrink-0 font-mono text-[11px] uppercase text-text-muted">
                            {source.type ?? 'unknown'}
                          </span>
                          <span className="w-20 shrink-0 text-right font-mono text-[11px] text-text-faint">
                            {source.chunks} chunks
                          </span>
                          <span className="w-40 shrink-0 text-right">
                            <StatusBadge
                              status={
                                source.status === 'indexed'
                                  ? 'ready'
                                  : source.status === 'failed'
                                    ? 'unavailable'
                                    : 'disabled'
                              }
                              label={source.status}
                              size="sm"
                            />
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          )
        }}
      </AsyncBoundary>
    </>
  )
}

function MemoryDetail({ id }: { id: string }) {
  const state = useApi(() => api.source(id), [id])

  return (
    <>
      <button
        type="button"
        onClick={() => navigate('/memories')}
        className="mb-4 text-[13px] text-text-muted transition-colors hover:text-text"
      >
        ← Memories
      </button>

      <AsyncBoundary state={state}>
        {(data) => (
          <div className="space-y-6">
            <Card>
              <CardHeader
                title={data.name}
                subtitle={data.source}
                action={
                  <StatusBadge
                    status={
                      data.status === 'indexed'
                        ? 'ready'
                        : data.status === 'failed'
                          ? 'unavailable'
                          : 'disabled'
                    }
                    label={data.status}
                    size="sm"
                  />
                }
              />
              <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
                {[
                  ['Filename', data.name],
                  ['Type', data.type ?? 'Unknown'],
                  ['Chunks', String(data.chunk_count)],
                  ['Last ingested', formatTimestamp(data.last_ingested)],
                ].map(([label, value]) => (
                  <div key={label} className="bg-surface px-5 py-4">
                    <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-faint">
                      {label}
                    </dt>
                    <dd className="mt-1.5 truncate font-mono text-[13px] text-text" title={value}>
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </Card>

            <Card>
              <CardHeader
                title="Indexed Chunks"
                subtitle={`${data.chunks.length} shown${data.chunks_truncated ? ` of ${data.chunk_count}` : ''}`}
              />
              {data.chunks.length === 0 ? (
                <EmptyState title="No chunk text exposed for this source." />
              ) : (
                <ul className="divide-y divide-border">
                  {data.chunks.map((chunk) => (
                    <li key={chunk.entry_id} className="px-5 py-4">
                      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-text-faint">
                        <span className="text-text-muted">chunk {chunk.chunk_index}</span>
                        {chunk.start_char !== null ? (
                          <span>
                            chars {chunk.start_char}–{chunk.end_char}
                          </span>
                        ) : null}
                        {chunk.metadata?.heading ? (
                          <span className="truncate">§ {chunk.metadata.heading}</span>
                        ) : null}
                      </div>
                      <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-text-muted">
                        {chunk.text}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  )
}
