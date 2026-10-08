import type { ReactNode } from 'react'

import type { HealthStatus } from '../../lib/types'

/** Surface used for every panel in the GUI. */
export function Card({
  children,
  className = '',
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div' | 'article'
}) {
  return (
    <Tag
      className={`rounded-card border border-border bg-surface transition-colors duration-150 ${className}`}
    >
      {children}
    </Tag>
  )
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h2 className="font-display text-[17px] font-medium tracking-tight text-text">
          {title}
        </h2>
        {subtitle ? <p className="mt-1 text-[13px] text-text-faint">{subtitle}</p> : null}
      </div>
      {action}
    </header>
  )
}

const STATUS_STYLES: Record<HealthStatus, string> = {
  ready: 'text-success',
  unavailable: 'text-warning',
  disabled: 'text-text-faint',
  unknown: 'text-text-faint',
}

const STATUS_WORDS: Record<HealthStatus, string> = {
  ready: 'Ready',
  unavailable: 'Unavailable',
  disabled: 'Disabled',
  unknown: 'Unknown',
}

/**
 * Status indicator.
 *
 * Never colour alone: the dot is decorative and the state is always spelled out
 * in text, and `role="status"` lets a screen reader announce a change.
 */
export function StatusBadge({
  status,
  label,
  size = 'md',
}: {
  status: HealthStatus
  label?: string
  size?: 'sm' | 'md'
}) {
  const text = label ?? STATUS_WORDS[status]
  const dotSize = size === 'sm' ? 'size-1.5' : 'size-2'
  const glyph = status === 'ready' ? '●' : status === 'unavailable' ? '▲' : '○'

  return (
    <span
      role="status"
      className={`inline-flex items-center gap-1.5 whitespace-nowrap ${
        size === 'sm' ? 'text-[11px]' : 'text-xs'
      } font-medium ${STATUS_STYLES[status]}`}
    >
      <span aria-hidden="true" className={dotSize}>
        {glyph}
      </span>
      {text}
    </span>
  )
}

/** The literal PAM uses when a value cannot be determined at runtime. */
export function NotAvailable({ className = '' }: { className?: string }) {
  return (
    <span className={`text-text-faint italic ${className}`}>
      Not available from the current PAM runtime
    </span>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 px-5 py-10 text-sm text-text-muted"
    >
      <span
        aria-hidden="true"
        className="size-3.5 animate-spin rounded-full border-2 border-border-strong border-t-accent"
      />
      {label}
    </div>
  )
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-start gap-2 px-5 py-10">
      <p className="text-sm font-medium text-text">{title}</p>
      {hint ? <p className="max-w-prose text-[13px] text-text-muted">{hint}</p> : null}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 px-5 py-8">
      <div>
        <p className="text-sm font-medium text-danger">Unable to load this information.</p>
        <p className="mt-1 max-w-prose font-mono text-xs break-words text-text-muted">{message}</p>
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-border-strong bg-elevated px-3 py-1.5 text-xs font-medium text-text transition-colors hover:border-accent hover:text-accent-soft"
        >
          Retry
        </button>
      ) : null}
    </div>
  )
}

/**
 * Resolve the four required view states for one panel.
 * Keeps every page's loading / empty / error / success handling identical.
 */
export function AsyncBoundary<T>({
  state,
  isEmpty,
  empty,
  children,
}: {
  state: { data: T | null; error: string | null; loading: boolean; reload: () => void }
  isEmpty?: (data: T) => boolean
  empty?: ReactNode
  children: (data: T) => ReactNode
}) {
  if (state.loading) return <LoadingState />
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />
  if (state.data === null) return <LoadingState />
  if (isEmpty?.(state.data)) return <>{empty ?? <EmptyState title="Nothing here yet." />}</>
  return <>{children(state.data)}</>
}
