import { PageHeader } from '../components/dashboard/MetricCard'
import {
  AsyncBoundary,
  Card,
  CardHeader,
  EmptyState,
  StatusBadge,
} from '../components/common/Card'
import { api } from '../lib/api'
import { formatTimestamp, useApi } from '../lib/hooks'
import { navigate, useRoute } from '../lib/router'
import type { ArtifactSummary } from '../lib/types'
import { ArtifactView } from './Generate'

export function Library() {
  const route = useRoute()
  const detailId = route.segments[1]

  return detailId ? <ArtifactDetail id={detailId} /> : <ArtifactList />
}

function kindStatus(kind: string): 'ready' | 'disabled' {
  return kind ? 'ready' : 'disabled'
}

function ArtifactList() {
  const state = useApi(() => api.listArtifacts(), [])

  return (
    <>
      <PageHeader
        title="Library"
        subtitle="Every artifact PAM has generated, newest last."
      />

      <AsyncBoundary state={state}>
        {(data) =>
          data.artifacts.length === 0 ? (
            <Card>
              <EmptyState
                title="No artifacts yet."
                hint="Generate flashcards, a quiz, a report, or a presentation first."
                action={
                  <button
                    type="button"
                    onClick={() => navigate('/generate')}
                    className="rounded-md border border-accent/40 bg-accent-dim px-3.5 py-2 text-[13px] font-medium text-accent-soft transition-colors hover:border-accent hover:bg-accent/20"
                  >
                    Generate something
                  </button>
                }
              />
            </Card>
          ) : (
            <Card>
              <CardHeader
                title="Artifacts"
                subtitle={`${data.total} artifact${data.total === 1 ? '' : 's'}`}
              />
              <ul className="divide-y divide-border">
                {data.artifacts.map((artifact) => (
                  <li key={artifact.artifact_id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/library/${artifact.artifact_id}`)}
                      className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors hover:bg-elevated/50"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-text">
                          {artifact.title}
                        </span>
                        <span className="mt-0.5 block truncate font-mono text-[11px] text-text-faint">
                          {artifact.job_id} · v{artifact.version}
                        </span>
                      </span>
                      <span className="shrink-0 font-mono text-[11px] text-text-muted">
                        {artifact.kind}
                      </span>
                      <span className="w-36 shrink-0 text-right font-mono text-[11px] text-text-faint">
                        {formatTimestamp(artifact.created_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )
        }
      </AsyncBoundary>
    </>
  )
}

function ArtifactDetail({ id }: { id: string }) {
  const artifact = useApi(() => api.getArtifact(id), [id])
  const versions = useApi(() => api.getArtifactVersions(id), [id])
  const provenance = useApi(() => api.getArtifactProvenance(id), [id])

  return (
    <>
      <button
        type="button"
        onClick={() => navigate('/library')}
        className="mb-4 text-[13px] text-text-muted transition-colors hover:text-text"
      >
        ← Library
      </button>

      <AsyncBoundary state={artifact}>
        {(data: ArtifactSummary) => (
          <div className="space-y-6">
            <Card>
              <CardHeader
                title={data.title}
                subtitle={`${data.kind} · v${data.version}`}
                action={<StatusBadge status={kindStatus(data.kind)} label={data.kind} size="sm" />}
              />
              <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
                {[
                  ['Job', data.job_id],
                  ['Model role', data.model_role],
                  ['Created', formatTimestamp(data.created_at)],
                  ['Updated', formatTimestamp(data.updated_at)],
                ].map(([label, value]) => (
                      <div key={label} className="bg-surface px-5 py-4">
                        <dt className="text-[13px] font-medium text-text-muted">
                          {label}
                        </dt>
                    <dd
                      className="mt-1.5 truncate font-mono text-[13px] text-text"
                      title={value}
                    >
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="px-5 py-5">
                <ArtifactView artifact={data} />
              </div>
            </Card>

            <AsyncBoundary state={versions}>
              {(versionData) =>
                versionData.versions.length > 1 ? (
                  <Card>
                    <CardHeader
                      title="Versions"
                      subtitle={`${versionData.versions.length} versions of this artifact`}
                    />
                    <ul className="divide-y divide-border">
                      {versionData.versions.map((row) => (
                        <li
                          key={row.artifact_id}
                          className="flex items-center gap-4 px-5 py-3 text-[13px]"
                        >
                          <span className="font-mono text-[11px] text-text-muted">
                            v{row.version}
                          </span>
                          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-text-faint">
                            {row.artifact_id}
                          </span>
                          <span className="font-mono text-[11px] text-text-faint">
                            {formatTimestamp(row.created_at)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                ) : null
              }
            </AsyncBoundary>

            <AsyncBoundary state={provenance}>
              {(provenanceData) => (
                <Card>
                  <CardHeader
                    title="Provenance"
                    subtitle={`${provenanceData.total} evidence link${provenanceData.total === 1 ? '' : 's'}`}
                  />
                  {provenanceData.records.length === 0 ? (
                    <EmptyState title="No provenance recorded." />
                  ) : (
                    <ul className="divide-y divide-border">
                      {provenanceData.records.map((record, index) => (
                        <li
                          key={`${record.source_id}-${record.chunk_index ?? index}`}
                          className="px-5 py-3 text-[13px]"
                        >
                          <span className="font-mono text-[11px] text-text-muted">
                            {record.role}
                          </span>{' '}
                          <span className="font-mono text-[12px] text-text">
                            {record.source_id}
                          </span>
                          {record.chunk_index !== null ? (
                            <span className="ml-2 font-mono text-[11px] text-text-faint">
                              chunk {record.chunk_index}
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              )}
            </AsyncBoundary>
          </div>
        )}
      </AsyncBoundary>
    </>
  )
}
