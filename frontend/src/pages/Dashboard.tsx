import { ActivityTimeline, SystemHealth } from '../components/dashboard/ActivityTimeline'
import { KnowledgeSources } from '../components/dashboard/KnowledgeSources'
import { PageHeader } from '../components/dashboard/MetricCard'
import { MetricCard } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, ErrorState, NotAvailable } from '../components/common/Card'
import { api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { navigate } from '../lib/router'
import { formatTimestamp } from '../lib/hooks'

export function Dashboard() {
  const system = useApi(() => api.system(), [])
  const activity = useApi(() => api.activity(8), [])
  const sources = useApi(() => api.sources(), [])

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Your personal knowledge system at a glance."
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

      {system.error ? (
        <Card className="mb-6 border-danger/30">
          <ErrorState message={system.error} onRetry={system.reload} />
        </Card>
      ) : null}

      <AsyncBoundary state={system}>
        {(data) => {
          if (!data.config_ok) {
            return (
              <Card>
                <CardHeader title="System" subtitle="Configuration could not be loaded" />
                <div className="px-5 py-6">
                  <p className="text-sm text-text-muted">
                    PAM could not load its configuration, so no runtime data can be shown.
                  </p>
                  <p className="mt-3 font-mono text-xs break-words text-danger">
                    {data.config_error}
                  </p>
                </div>
              </Card>
            )
          }

          const m = data.metrics
          const unavailable = m.sources === null || m.chunks === null

          return (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  value={m.sources ?? '—'}
                  label="Sources"
                  hint="Indexed sources"
                  unavailable={m.sources === null}
                />
                <MetricCard
                  value={m.chunks ?? '—'}
                  label="Memory Chunks"
                  hint="Indexed chunks"
                  unavailable={m.chunks === null}
                />
                <MetricCard
                  value={data.retrieval?.top_k_default ?? '—'}
                  label="Retrieval Top-K"
                  hint="Current config"
                  unavailable={data.retrieval === null}
                />
                <MetricCard
                  value={
                    <span className="text-[20px] uppercase">{data.state}</span>
                  }
                  label="System"
                  hint="Runtime status"
                  unavailable={data.state === 'unknown'}
                />
              </div>

              {unavailable ? (
                <Card className="border-warning/30">
                  <div className="px-5 py-4 text-[13px] text-text-muted">
                    Some counts could not be read from the vector store. <NotAvailable />
                  </div>
                </Card>
              ) : null}

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                <div className="space-y-6 xl:col-span-2">
                  <ActivityTimeline
                    events={activity.data?.events ?? []}
                    available={activity.data?.available ?? false}
                  />
                  <AsyncBoundary state={sources}>
                    {(data2) => (
                      <KnowledgeSources
                        slices={data2.by_type.map(([name, chunks]) => ({ name, chunks }))}
                        totalChunks={data2.total_chunks}
                      />
                    )}
                  </AsyncBoundary>
                </div>

                <div className="space-y-6">
                  <SystemHealth health={data.health} />

                  <Card>
                    <CardHeader title="Ledger" subtitle="Durable ingestion record" />
                    <dl className="divide-y divide-border text-[13px]">
                      {[
                        ['Ledger entries', m.ledger_entries],
                        ['Successful ingests', m.processed],
                        ['Skipped duplicates', m.skipped_duplicates],
                        ['Failed', m.failed],
                      ].map(([label, value]) => (
                        <div key={label as string} className="flex items-center justify-between gap-4 px-5 py-2.5">
                          <dt className="text-text-muted">{label}</dt>
                          <dd className="font-mono text-text">
                            {value === null ? (
                              <span className="text-text-faint italic">Not available</span>
                            ) : (
                              value
                            )}
                          </dd>
                        </div>
                      ))}
                      <div className="flex items-center justify-between gap-4 px-5 py-2.5">
                        <dt className="text-text-muted">Last ingestion</dt>
                        <dd className="font-mono text-xs text-text">
                          {data.activity?.latest ? (
                            formatTimestamp(data.activity.latest)
                          ) : (
                            <span className="text-text-faint italic">Never</span>
                          )}
                        </dd>
                      </div>
                    </dl>
                  </Card>
                </div>
              </div>
            </div>
          )
        }}
      </AsyncBoundary>
    </>
  )
}
