import { api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { navigate } from '../../lib/router'

/**
 * Top bar identity and runtime state.
 *
 * "Healthy" is only shown when PAM's own health endpoint says so. When the
 * configuration cannot load, or the model runtime cannot be reached, this
 * reports that instead of a reassuring green dot.
 */
export function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const { data } = useApi(() => api.health(), [])

  const state = data?.state ?? 'unknown'
  const detail = data?.config_error ?? data?.detail ?? null

  const badge =
    state === 'healthy'
      ? { glyph: '●', word: 'LOCAL · HEALTHY', tone: 'text-success', title: 'PAM is running locally and the model runtime responded.' }
      : state === 'degraded'
        ? { glyph: '▲', word: 'LOCAL · DEGRADED', tone: 'text-warning', title: detail ?? 'The local model runtime could not be reached.' }
        : { glyph: '○', word: 'STATUS UNKNOWN', tone: 'text-text-faint', title: detail ?? 'PAM has not reported a status.' }

  return (
    <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-bg px-5 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenNav}
          aria-label="Open navigation"
          className="rounded-md border border-border px-2 py-1 text-xs text-text-muted transition-colors hover:border-accent hover:text-accent-soft lg:hidden"
        >
          ☰
        </button>
        <div className="min-w-0">
          <p className="text-[13px] font-semibold tracking-wide text-text">PAM</p>
          <p className="truncate text-[11px] text-text-faint">Personal AI Memory</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => navigate('/search')}
          className="hidden items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[11px] text-text-faint transition-colors hover:border-border-strong hover:text-text-muted sm:flex"
        >
          <span aria-hidden="true">⌕</span>
          <span>Search</span>
          <kbd className="rounded border border-border bg-elevated px-1 font-mono text-[10px] text-text-faint">
            Ctrl+K
          </kbd>
        </button>

        <button
          type="button"
          onClick={() => navigate('/diagnostics')}
          aria-label="Diagnostics and system status"
          title="Diagnostics"
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-[11px] text-text-faint transition-colors hover:border-border-strong hover:text-text-muted"
        >
          ?
        </button>

        <button
          type="button"
          onClick={() => navigate('/configuration')}
          aria-label="Settings"
          title="Settings"
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-[11px] text-text-faint transition-colors hover:border-border-strong hover:text-text-muted"
        >
          ⚙
        </button>

        <span
          role="status"
          title={badge.title}
          className={`flex items-center gap-1.5 whitespace-nowrap rounded-md border border-border bg-surface px-2.5 py-1.5 text-[11px] font-medium ${badge.tone}`}
        >
          <span aria-hidden="true">{badge.glyph}</span>
          <span className="hidden sm:inline">{badge.word}</span>
          <span className="sm:hidden">{state === 'unknown' ? 'UNKNOWN' : state.toUpperCase()}</span>
        </span>
      </div>
    </header>
  )
}
