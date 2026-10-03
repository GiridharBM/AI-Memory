import { navigate, useRoute } from '../../lib/router'

interface NavItem {
  label: string
  path: string
  icon: string
}

interface NavGroup {
  heading: string
  items: NavItem[]
}

const GROUPS: NavGroup[] = [
  {
    heading: 'Workspace',
    items: [
      { label: 'Dashboard', path: '/dashboard', icon: '▦' },
      { label: 'Ask PAM', path: '/ask', icon: '◈' },
      { label: 'Search', path: '/search', icon: '⌕' },
      { label: 'Memories', path: '/memories', icon: '❑' },
      { label: 'Ingest', path: '/ingest', icon: '↧' },
      { label: 'Generate', path: '/generate', icon: '✦' },
      { label: 'Library', path: '/library', icon: '▤' },
      { label: 'Mind Map', path: '/mindmap', icon: '⁂' },
    ],
  },
  {
    heading: 'Intelligence',
    items: [
      { label: 'Evaluation', path: '/evaluation', icon: '◎' },
      { label: 'Retrieval', path: '/retrieval', icon: '⇅' },
      { label: 'Activity', path: '/activity', icon: '≣' },
    ],
  },
  {
    heading: 'System',
    items: [
      { label: 'Diagnostics', path: '/diagnostics', icon: '✚' },
      { label: 'Configuration', path: '/configuration', icon: '⚙' },
      { label: 'Storage', path: '/storage', icon: '▤' },
    ],
  },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const route = useRoute()
  const active = route.segments[0] ?? 'dashboard'

  const go = (path: string) => {
    navigate(path)
    onNavigate?.()
  }

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-60 shrink-0 flex-col border-r border-border bg-surface max-lg:w-52"
    >
      <div className="border-b border-border px-5 py-5">
        <div className="flex items-center gap-2.5">
          {/* Geometric memory node: a centre point with three linked nodes. */}
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="size-6 shrink-0 text-accent"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
            <circle cx="4" cy="5" r="2" />
            <circle cx="20" cy="6" r="2" />
            <circle cx="17" cy="19" r="2" />
            <path d="M10.2 10.6 5.6 6.4M13.9 10.5l4.6-3.3M13.4 13.9l2.8 3.7" />
          </svg>
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-wide text-text">PAM</p>
            <p className="truncate text-[11px] text-text-faint">Personal AI Memory</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        {GROUPS.map((group) => (
          <div key={group.heading} className="mb-5 last:mb-0">
            <h2 className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-faint">
              {group.heading}
            </h2>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = active === item.path.slice(1)
                return (
                  <li key={item.path}>
                    <a
                      href={`#${item.path}`}
                      aria-current={isActive ? 'page' : undefined}
                      onClick={(event) => {
                        event.preventDefault()
                        go(item.path)
                      }}
                      className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors duration-150 ${
                        isActive
                          ? 'bg-elevated text-text'
                          : 'text-text-muted hover:bg-elevated/60 hover:text-text'
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`w-4 shrink-0 text-center text-[13px] ${
                          isActive ? 'text-accent' : 'text-text-faint'
                        }`}
                      >
                        {item.icon}
                      </span>
                      {item.label}
                    </a>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-border p-3">
        <a
          href="#/settings"
          onClick={(event) => {
            event.preventDefault()
            go('/configuration')
          }}
          className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-text-muted transition-colors hover:bg-elevated/60 hover:text-text"
        >
          <span aria-hidden="true" className="w-4 text-center text-[13px] text-text-faint">
            ⚙
          </span>
          Settings
        </a>
      </div>
    </nav>
  )
}
