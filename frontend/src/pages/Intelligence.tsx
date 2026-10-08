import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, EmptyState, NotAvailable, StatusBadge } from '../components/common/Card'
import { ApiError, api } from '../lib/api'
import { formatBytes, formatTimestamp, useApi } from '../lib/hooks'
import { RetrievalPipeline } from '../components/retrieval/RetrievalPipeline'

/** Retrieval pipeline inspector: what is actually enabled, from config. */
export function Retrieval() {
  const state = useApi(() => api.retrieval(), [])
  const flags = useApi(() => api.retrievalFlags(), [])
  const [toggling, setToggling] = useState<string | null>(null)
  const [toggleError, setToggleError] = useState<string | null>(null)

  async function onToggleStage(stageId: 'hyde' | 'rerank' | 'answerability') {
    if (toggling !== null || flags.data === null) return
    const field =
      stageId === 'hyde' ? 'hyde_enabled' : stageId === 'rerank' ? 'reranker_enabled' : 'answerability_enabled'
    setToggling(stageId)
    setToggleError(null)
    try {
      // The backend returns the canonical state; both views reload from it
      // so the UI can never disagree with the runtime configuration.
      await api.updateRetrievalFlags({ [field]: !flags.data[field] })
      flags.reload()
      state.reload()
    } catch (cause) {
      setToggleError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setToggling(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Retrieval"
        subtitle="How PAM turns a query into evidence, as currently configured."
      />
      <AsyncBoundary state={state}>
        {(data) =>
          !data.available ? (
            <Card className="border-danger/30">
              <CardHeader title="Retrieval" />
              <p className="px-5 py-4 text-[13px] text-text-muted">{data.config_error}</p>
            </Card>
          ) : (
            <div className="space-y-6">
              <Card>
                <CardHeader
                  title="Pipeline"
                  subtitle="Stages drawn from the running configuration; disabled stages are shown as disabled"
                />
                <RetrievalPipeline
                  config={data}
                  detail
                  toggle={
                    flags.data === null
                      ? null
                      : {
                          busy: toggling !== null,
                          onToggle: (stageId) => void onToggleStage(stageId),
                        }
                  }
                />
                {toggleError ?? flags.error ? (
                  <p role="alert" className="px-5 pb-4 text-[13px] text-danger">
                    {toggleError ?? flags.error}
                  </p>
                ) : null}
              </Card>

              <Card>
                <CardHeader title="Parameters" />
                <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3">
                  {(
                    [
                      ['RRF k', data.rrf_k],
                      ['Top-K default', data.top_k_default],
                      ['Min cosine', data.min_cosine],
                      ['QA timeout', `${data.qa_timeout_seconds}s`],
                      ['Ollama num_ctx', data.ollama_num_ctx],
                    ] as [string, string | number][]
                  ).map(([label, value]) => (
                    <div key={label} className="bg-surface px-5 py-4">
                      <dt className="text-[13px] font-medium text-text-muted">
                        {label}
                      </dt>
                      <dd className="mt-1.5 font-mono text-sm text-text">{value}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </div>
          )
        }
      </AsyncBoundary>
    </>
  )
}

/** Ingestion activity from the durable ledger. */
export function Activity() {
  const state = useApi(() => api.activity(200), [])

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle="Ingestion events recorded in PAM's durable manifest ledger."
      />
      <Card className="mb-6">
        <p className="px-5 py-3.5 text-[13px] text-text-muted">
          PAM records ingestion events only. Searches, QA queries, configuration
          changes and diagnostic runs are not persisted, so they do not appear here.
        </p>
      </Card>

      <AsyncBoundary state={state}>
        {(data) => (
          <Card>
            <CardHeader
              title="Ledger"
              subtitle={data.available ? `${data.total ?? data.events.length} recorded events` : 'Unavailable'}
            />
            {!data.available ? (
              <p className="px-5 py-5 text-[13px]">
                <NotAvailable />
              </p>
            ) : data.events.length === 0 ? (
              <EmptyState
                title="No recent activity"
                hint="Activity will appear here as you use PAM."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-border text-[13px] text-text-faint">
                      <th scope="col" className="px-5 py-2.5 font-semibold">When</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Source</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Status</th>
                      <th scope="col" className="px-5 py-2.5 text-right font-semibold">Chunks</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {data.events.map((event, index) => (
                      <tr key={`${event.at}-${event.filename}-${index}`}>
                        <td className="px-5 py-2.5 font-mono text-[11px] whitespace-nowrap text-text-faint">
                          {formatTimestamp(event.at)}
                        </td>
                        <td className="max-w-72 truncate px-5 py-2.5 text-text">
                          {event.filename ?? '—'}
                        </td>
                        <td className="px-5 py-2.5">
                          <StatusBadge
                            status={
                              event.status === 'processed'
                                ? 'ready'
                                : event.status === 'failed'
                                  ? 'unavailable'
                                  : 'disabled'
                            }
                            label={event.status}
                            size="sm"
                          />
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-xs text-text-muted">
                          {event.chunks_stored ?? '—'}
                        </td>
                        <td className="max-w-56 truncate px-5 py-2.5 font-mono text-[11px] text-text-faint">
                          {event.error_reason ?? event.note ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </AsyncBoundary>
      <GenerationJobs />
    </>
  )
}

/** Generation jobs from the V2 job store. */
function GenerationJobs() {
  const state = useApi(() => api.listJobs(), [])

  return (
    <div className="mt-6">
      <AsyncBoundary state={state}>
        {(data) =>
          data.jobs.length === 0 ? (
            <Card>
              <EmptyState
                title="No generation jobs yet."
                hint="Submit a request from Generate to see it tracked here."
              />
            </Card>
          ) : (
            <Card>
              <CardHeader
                title="Generation jobs"
                subtitle={`${data.total} tracked job${data.total === 1 ? '' : 's'}`}
              />
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-border text-[13px] text-text-faint">
                      <th scope="col" className="px-5 py-2.5 font-semibold">When</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Task</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Status</th>
                      <th scope="col" className="px-5 py-2.5 text-right font-semibold">Progress</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Stage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {data.jobs.map((job) => (
                      <tr key={job.job_id}>
                        <td className="px-5 py-2.5 font-mono text-[11px] whitespace-nowrap text-text-faint">
                          {formatTimestamp(job.created_at)}
                        </td>
                        <td className="px-5 py-2.5 font-mono text-[11px] text-text-muted">
                          {job.task_type}
                        </td>
                        <td className="px-5 py-2.5">
                          <StatusBadge
                            status={
                              job.status === 'done'
                                ? 'ready'
                                : job.status === 'failed'
                                  ? 'unavailable'
                                  : 'disabled'
                            }
                            label={job.status}
                            size="sm"
                          />
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-xs text-text-muted">
                          {job.progress}%
                        </td>
                        <td className="max-w-56 truncate px-5 py-2.5 font-mono text-[11px] text-text-faint">
                          {job.stage || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )
        }
      </AsyncBoundary>
    </div>
  )
}

/** Offline evaluation artifacts. No metrics are invented. */
export function Evaluation() {
  const state = useApi(() => api.evaluation(), [])

  return (
    <>
      <PageHeader
        title="Evaluation"
        subtitle="PAM's evaluation corpus and frozen experiment artifacts."
      />

      <Card className="mb-6">
        <p className="px-5 py-3.5 text-[13px] text-text-muted">
          PAM evaluates offline against frozen corpora; there is no runtime
          evaluation service. Headline metrics are{' '}
          <span className="text-text">Not available</span> from a running system,
          so only the real artifact inventory is listed below.
        </p>
      </Card>

      <AsyncBoundary state={state}>
        {(data) => (
          <Card>
            <CardHeader
              title="Experiment Artifacts"
              subtitle={
                data.available
                  ? `${data.artifact_count} files in ${data.results_dir}`
                  : undefined
              }
            />
            {!data.available ? (
              <p className="px-5 py-5 text-[13px]">
                <NotAvailable />
              </p>
            ) : (data.artifacts?.length ?? 0) === 0 ? (
              <EmptyState title="No evaluation artifacts found." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-border text-[13px] text-text-faint">
                      <th scope="col" className="px-5 py-2.5 font-semibold">Artifact</th>
                      <th scope="col" className="px-5 py-2.5 font-semibold">Kind</th>
                      <th scope="col" className="px-5 py-2.5 text-right font-semibold">Size</th>
                      <th scope="col" className="px-5 py-2.5 text-right font-semibold">Metrics</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {data.artifacts?.map((artifact) => (
                      <tr key={artifact.name}>
                        <td className="px-5 py-2.5 font-mono text-xs text-text">
                          {artifact.name}
                        </td>
                        <td className="px-5 py-2.5 font-mono text-[11px] text-text-faint">
                          {artifact.kind}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-xs text-text-muted">
                          {formatBytes(artifact.size_bytes)}
                        </td>
                        <td className="px-5 py-2.5 text-right text-[11px] text-text-faint italic">
                          Not available
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </AsyncBoundary>
    </>
  )
}

/** Resolved configuration, straight from PAM's authoritative Settings model. */
export function Configuration() {
  const state = useApi(() => api.config(), [])

  return (
    <>
      <PageHeader
        title="Configuration"
        subtitle="The configuration PAM actually resolved at runtime."
      />
      <Card className="mb-6">
        <p className="px-5 py-3.5 text-[13px] text-text-muted">
          Read-only. PAM configuration stays backend-authoritative and is never
          round-tripped through the browser, so this view cannot drift from what
          the running system uses.
        </p>
      </Card>

      <AsyncBoundary state={state}>
        {(data) =>
          !data.available ? (
            <Card className="border-danger/30">
              <CardHeader title="Configuration" />
              <p className="px-5 py-4 text-[13px] text-text-muted">{data.config_error}</p>
            </Card>
          ) : (
            <div className="space-y-4">
              {Object.entries(data.config ?? {}).map(([section, value]) => (
                <Card key={section}>
                  <CardHeader title={section} />
                  <ConfigTree node={value} depth={0} />
                </Card>
              ))}
            </div>
          )
        }
      </AsyncBoundary>
    </>
  )
}

function ConfigTree({ node, depth }: { node: unknown; depth: number }) {
  if (node === null || node === undefined) {
    return (
      <div className="flex gap-3 px-5 py-1.5" style={{ paddingLeft: 20 + depth * 14 }}>
        <span className="text-text-faint italic">Not available</span>
      </div>
    )
  }

  if (Array.isArray(node)) {
    if (node.length === 0) {
      return (
        <div className="px-5 py-1.5 font-mono text-xs text-text-faint" style={{ paddingLeft: 20 + depth * 14 }}>
          (empty)
        </div>
      )
    }
    return (
      <ul>
        {node.map((item, index) => (
          <li key={index} className="px-5 py-1 font-mono text-xs text-text-muted" style={{ paddingLeft: 20 + depth * 14 }}>
            {typeof item === 'object' ? JSON.stringify(item) : String(item)}
          </li>
        ))}
      </ul>
    )
  }

  if (typeof node === 'object') {
    return (
      <ul className="py-1">
        {Object.entries(node as Record<string, unknown>).map(([key, value]) => (
          <li key={key}>
            {typeof value === 'object' && value !== null ? (
              <>
                <p
                  className="pt-2 pb-0.5 text-[13px] font-medium text-text-muted"
                  style={{ paddingLeft: 20 + depth * 14 }}
                >
                  {key}
                </p>
                <ConfigTree node={value} depth={depth + 1} />
              </>
            ) : (
              <div
                className="flex flex-wrap items-baseline gap-x-3 px-5 py-1"
                style={{ paddingLeft: 20 + depth * 14 }}
              >
                <span className="text-[12px] text-text-muted">{key}</span>
                <span className="font-mono text-xs break-all text-text">
                  {typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value)}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="px-5 py-1 font-mono text-xs text-text" style={{ paddingLeft: 20 + depth * 14 }}>
      {String(node)}
    </div>
  )
}
