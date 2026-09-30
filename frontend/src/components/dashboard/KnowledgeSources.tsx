import { Card, CardHeader, EmptyState } from '../common/Card'

export interface TypeSlice {
  name: string
  chunks: number
}

/**
 * Source-type distribution.
 *
 * The slices come from `source_type` on the entries PAM actually holds, so this
 * shows what is indexed rather than what the system claims it could accept.
 */
export function KnowledgeSources({
  slices,
  totalChunks,
}: {
  slices: TypeSlice[]
  totalChunks: number | null
}) {
  if (slices.length === 0) {
    return (
      <Card>
        <CardHeader title="Knowledge Sources" subtitle="Distribution by indexed source type" />
        <EmptyState
          title="No indexed sources yet"
          hint="Ingest a document and its source type will appear here."
        />
      </Card>
    )
  }

  const max = Math.max(...slices.map((slice) => slice.chunks))

  return (
    <Card>
      <CardHeader
        title="Knowledge Sources"
        subtitle={
          totalChunks === null
            ? 'Distribution by indexed source type'
            : `${totalChunks} chunks across ${slices.length} source type${slices.length === 1 ? '' : 's'}`
        }
      />
      <ul className="space-y-2.5 px-5 py-4">
        {slices.map((slice) => (
          <li key={slice.name} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3">
            <span className="truncate font-mono text-[11px] uppercase tracking-wide text-text-muted">
              {slice.name}
            </span>
            <span
              aria-hidden="true"
              className="h-1.5 overflow-hidden rounded-full bg-elevated"
            >
              <span
                className="block h-full rounded-full bg-accent/70"
                style={{ width: `${Math.max(3, (slice.chunks / max) * 100)}%` }}
              />
            </span>
            <span className="w-12 text-right font-mono text-[11px] text-text-faint">
              {slice.chunks}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
