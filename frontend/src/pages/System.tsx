import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, NotAvailable, StatusBadge } from '../components/common/Card'
import { api } from '../lib/api'
import { formatBytes, useApi } from '../lib/hooks'

/** Engineering diagnostics: environment, models, retrieval, storage. */
export function Diagnostics() {
  const state = useApi(() => api.diagnostics(), [])

  return (
    <>
      <PageHeader title="Diagnostics" subtitle="Environment, models, retrieval and storage." />

      <AsyncBoundary state={state}>
        {(data) =>
          !data.available || !data.environment || !data.models || !data.retrieval || !data.ingestion || !data.storage ? (
            <Card className="border-danger/30">
              <CardHeader title="Diagnostics" />
              <p className="px-5 py-4 text-[13px] text-text-muted">{data.config_error}</p>
            </Card>
          ) : (
            <div className="space-y-6">
              <Card>
                <CardHeader title="Environment" />
                <Rows
                  rows={[
                    ['Python', data.environment.python],
                    ['Platform', data.environment.platform],
                    ['PAM version', data.environment.pam_version ?? 'Not available'],
                    ['Environment', data.environment.environment],
                    ['Config file', data.environment.config_file],
                  ]}
                />
              </Card>

              <Card>
                <CardHeader title="Models" />
                <Rows
                  rows={[
                    ['LLM', data.models.llm],
                    ['Embeddings', data.models.embeddings],
                    ['Vision', data.models.vision],
                    ['Audio', data.models.audio],
                    ['Ollama host', data.models.ollama_host],
                    ['Ollama num_ctx', String(data.models.ollama_num_ctx)],
                  ]}
                />
                <div className="border-t border-border px-5 py-3">
                  <StatusBadge
                    status={data.models.ollama_reachable ? 'ready' : 'unavailable'}
                    label={
                      data.models.ollama_reachable
                        ? data.models.ollama_model_present === false
                          ? `Reachable, but ${data.models.llm} is not listed`
                          : 'Reachable'
                        : 'Unreachable'
                    }
                  />
                  {data.models.ollama_detail ? (
                    <p className="mt-1.5 font-mono text-[11px] text-text-faint">
                      {data.models.ollama_detail}
                    </p>
                  ) : null}
                </div>
              </Card>

              <Card>
                <CardHeader title="Retrieval" />
                <Rows
                  rows={[
                    ['RRF k', String(data.retrieval.rrf_k)],
                    ['Top-K default', String(data.retrieval.top_k_default)],
                    ['Abstention min cosine', String(data.retrieval.min_cosine)],
                    ['QA timeout', `${data.retrieval.qa_timeout_seconds}s`],
                    ['Reranker', data.retrieval.reranker_enabled ? data.retrieval.reranker_model : 'Disabled'],
                    ['HyDE', data.retrieval.hyde_enabled ? 'Enabled' : 'Disabled'],
                    ['Answerability gate', data.retrieval.answerability_enabled ? 'Enabled' : 'Disabled'],
                  ]}
                />
              </Card>

              <Card>
                <CardHeader title="Ingestion" />
                <Rows
                  rows={[
                    ['Watcher', data.ingestion.watcher_enabled ? 'Enabled' : 'Disabled'],
                    ['OCR', data.ingestion.ocr_enabled ? `Enabled (${data.ingestion.ocr_engine})` : 'Disabled'],
                    ['OCR page limit', data.ingestion.ocr_page_limit === 0 ? 'all pages' : String(data.ingestion.ocr_page_limit)],
                    ['Metadata extraction', data.ingestion.metadata_enabled ? 'Enabled' : 'Disabled'],
                    ['Watcher extensions', data.ingestion.watcher_extensions.join(', ')],
                  ]}
                />
              </Card>

              <Card>
                <CardHeader title="Storage" />
                <Rows
                  rows={[
                    ['Sources', data.storage.sources === null ? 'Not available' : String(data.storage.sources)],
                    ['Chunks', data.storage.chunks === null ? 'Not available' : String(data.storage.chunks)],
                  ]}
                />
                <ul className="divide-y divide-border border-t border-border">
                  {data.storage.directories.map((directory) => (
                    <li key={directory.label} className="flex items-center justify-between gap-4 px-5 py-2.5">
                      <span className="min-w-0">
                        <span className="block text-[13px] text-text-muted">{directory.label}</span>
                        <span className="block truncate font-mono text-[11px] text-text-faint">
                          {directory.detail}
                        </span>
                      </span>
                      <StatusBadge
                        status={directory.ok ? 'ready' : 'unavailable'}
                        label={directory.ok ? 'Writable' : 'Not writable'}
                        size="sm"
                      />
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          )
        }
      </AsyncBoundary>
    </>
  )
}

/** Storage overview: locations, artifacts and persistence state. */
export function Storage() {
  const state = useApi(() => api.storage(), [])

  return (
    <>
      <PageHeader title="Storage" subtitle="Where PAM keeps its data, and how much of it there is." />

      <AsyncBoundary state={state}>
        {(data) =>
          !data.available ? (
            <Card className="border-danger/30">
              <CardHeader title="Storage" />
              <p className="px-5 py-4 text-[13px] text-text-muted">{data.config_error}</p>
            </Card>
          ) : (
            <div className="space-y-6">
              <Card>
                <CardHeader title="Vector Store" subtitle="The retrieval index" />
                <Rows
                  rows={[
                    ['Type', data.vector_store.type],
                    ['Sources', data.vector_store.sources === null ? 'Not available' : String(data.vector_store.sources)],
                    ['Chunks', data.vector_store.chunks === null ? 'Not available' : String(data.vector_store.chunks)],
                    ['Size on disk', formatBytes(data.vector_store.size_bytes)],
                    ['Path', data.vector_store.path],
                  ]}
                />
              </Card>

              <Card>
                <CardHeader title="Artifacts" />
                <Rows
                  rows={[
                    [
                      'Knowledge graph',
                      data.knowledge_graph.exists
                        ? formatBytes(data.knowledge_graph.size_bytes)
                        : 'Not present',
                    ],
                    [
                      'Manifest ledger',
                      data.manifest.entries === null
                        ? 'Not available'
                        : `${data.manifest.entries} entries`,
                    ],
                    ['Manifest enabled', data.manifest.enabled ? 'Yes' : 'No'],
                    ['Manifest path', data.manifest.path],
                    ['Vault notes', String(data.vault.notes)],
                  ]}
                />
              </Card>

              <Card>
                <CardHeader title="Paths" subtitle="Resolved from PAM configuration" />
                <Rows rows={Object.entries(data.paths)} />
              </Card>
            </div>
          )
        }
      </AsyncBoundary>
    </>
  )
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-border">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-start justify-between gap-4 px-5 py-2.5">
          <dt className="shrink-0 text-[13px] text-text-muted">{label}</dt>
          <dd className="min-w-0 text-right font-mono text-xs break-all text-text">
            {value === 'Not available' ? (
              <span className="text-text-faint italic">{value}</span>
            ) : (
              value
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export { NotAvailable }
