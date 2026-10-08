import type { ReactNode } from 'react'

/** Page title block. `action` carries the page's primary control. */
export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-[28px] leading-tight font-medium tracking-tight text-text">
          {title}
        </h1>
        {subtitle ? <p className="mt-1.5 text-sm text-text-muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  )
}

/**
 * Dashboard metric tile.
 *
 * `value` accepts a pre-rendered node so a tile can show the literal
 * "Not available" treatment instead of a number PAM could not determine.
 */
export function MetricCard({
  value,
  label,
  hint,
  unavailable = false,
}: {
  value: ReactNode
  label: string
  hint: string
  unavailable?: boolean
}) {
  return (
    <article className="rounded-card border border-border bg-surface p-5 transition-colors duration-150 hover:border-border-strong">
      <p
        className={`font-display text-[32px] leading-none tracking-tight ${
          unavailable ? 'text-text-faint' : 'text-text'
        }`}
      >
        {value}
      </p>
      <p className="mt-3 text-[13px] font-medium text-text-muted">{label}</p>
      <p className="mt-1 text-xs text-text-faint">{hint}</p>
    </article>
  )
}
