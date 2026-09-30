import { Card, CardHeader, EmptyState, NotAvailable, StatusBadge } from '../common/Card'
import type { ActivityEvent, HealthItem } from '../../lib/types'
import { formatTimestamp } from '../../lib/hooks'
import type { HealthStatus } from '../../lib/types'

/**
 * Knowledge Activity timeline, built from PAM's durable ingestion ledger.
 *
 * PAM persists ingest events only — searches, QA queries and configuration
 * changes are not recorded — so the panel is scoped and labelled as ingestion
 * activity rather than implying a full audit trail.
 */
export function ActivityTimeline({ events, available }: { events: ActivityEvent[]; available: boolean }) {
  if (!available) {
    return (
      <Card>
        <CardHeader title="Knowledge Activity" subtitle="From the durable ingestion ledger" />
        <div className="px-5 py-6">
          <NotAvailable />
        </div>
      </Card>
    )
  }

  if (events.length === 0) {
    return (
      <Card>
        <CardHeader title="Knowledge Activity" subtitle="From the durable ingestion ledger" />
        <EmptyState
          title="No recent activity"
          hint="Activity will appear here as you use PAM."
        />
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader
        title="Knowledge Activity"
        subtitle="Ingestion events recorded in the durable ledger"
      />
      <ol className="relative px-5 py-4">
        {events.map((event, index) => (
          <li key={`${event.at}-${event.filename}-${index}`} className="relative flex gap-4 pb-5 last:pb-0">
            {index < events.length - 1 ? (
              <span
                aria-hidden="true"
                className="absolute top-4 bottom-0 left-[5px] w-px bg-border"
              />
            ) : null}
            <span
              aria-hidden="true"
              className={`relative mt-1.5 size-2.5 shrink-0 rounded-full border-2 border-surface ${
                event.status === 'failed'
                  ? 'bg-danger'
                  : event.status === 'skipped_duplicate'
                    ? 'bg-warning'
                    : 'bg-success'
              }`}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p className="truncate text-[13px] font-medium text-text">
                  {event.filename ?? 'Unknown source'}
                </p>
                <time className="shrink-0 font-mono text-[11px] text-text-faint">
                  {formatTimestamp(event.at)}
                </time>
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
                <StatusBadge status={event.status === 'processed' ? 'ready' : event.status === 'failed' ? 'unavailable' : 'disabled'} label={event.status} size="sm" />
                {event.chunks_stored !== null ? (
                  <span className="font-mono">{event.chunks_stored} chunks</span>
                ) : null}
                {event.extension ? <span className="font-mono text-text-faint">{event.extension}</span> : null}
              </p>
              {event.error_reason ? (
                <p className="mt-1.5 font-mono text-[11px] break-words text-danger">
                  {event.error_reason}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

/** Real runtime status for LLM, embeddings, vector store, BM25 and RRF. */
export function SystemHealth({ health }: { health: Record<string, HealthItem> }) {
  const items = Object.values(health)

  return (
    <Card className="h-full">
      <CardHeader title="System Health" subtitle="Live runtime status" />
      {items.length === 0 ? (
        <div className="px-5 py-6">
          <NotAvailable />
        </div>
      ) : (
        <dl className="divide-y divide-border">
          {items.map((item) => (
            <div key={item.label} className="flex items-center justify-between gap-4 px-5 py-3">
              <dt className="min-w-0">
                <span className="block text-[13px] text-text-muted">{item.label}</span>
                {item.detail ? (
                  <span className="mt-0.5 block truncate font-mono text-[11px] text-text-faint">
                    {item.detail}
                  </span>
                ) : null}
              </dt>
              <dd className="flex shrink-0 items-center gap-3">
                <span className="font-mono text-xs text-text">
                  {item.value ?? <span className="text-text-faint italic">Not available</span>}
                </span>
                <StatusBadge status={item.status as HealthStatus} size="sm" />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  )
}
