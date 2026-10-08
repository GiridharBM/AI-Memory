import { useEffect, useState } from 'react'

import { Sidebar } from './components/layout/Sidebar'
import { TopBar } from './components/layout/TopBar'
import { NotAvailable } from './components/common/Card'
import { useRoute } from './lib/router'
import { Dashboard } from './pages/Dashboard'
import { Ask } from './pages/Ask'
import { Search } from './pages/Search'
import { Conversations } from './pages/Conversations'
import { Memories } from './pages/Memories'
import { Ingest } from './pages/Ingest'
import { Generate } from './pages/Generate'
import { Library } from './pages/Library'
import { MindMap } from './pages/MindMap'
import { MemoryReview } from './pages/MemoryReview'
import { Activity, Configuration, Evaluation, Retrieval } from './pages/Intelligence'
import { Diagnostics, Storage } from './pages/System'

const TITLES: Record<string, string> = {
  dashboard: 'Dashboard',
  ask: 'Ask PAM',
  search: 'Search',
  conversations: 'Conversations',
  memories: 'Memories',
  'memory-review': 'Memory Review',
  ingest: 'Add Knowledge',
  generate: 'Generate',
  library: 'Library',
  mindmap: 'Mind Map',
  evaluation: 'Evaluation',
  retrieval: 'Retrieval',
  activity: 'Activity',
  diagnostics: 'Diagnostics',
  configuration: 'Configuration',
  storage: 'Storage',
}

export default function App() {
  const route = useRoute()
  const [navOpen, setNavOpen] = useState(false)

  const section = route.segments[0] ?? 'dashboard'

  // Ctrl+K / Cmd+K focuses search from anywhere.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        window.location.hash = '/search'
      }
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    document.title = `${TITLES[section] ?? 'PAM'} — PAM`
  }, [section])

  return (
    <div className="flex h-dvh overflow-hidden bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:border focus:border-accent focus:bg-surface focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>

      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {navOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
            className="absolute inset-0 bg-black/60"
          />
          <div className="relative h-full w-60 animate-[fade-in_120ms_ease-out]">
            <Sidebar onNavigate={() => setNavOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenNav={() => setNavOpen(true)} />
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-5 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Page section={section} />
          </div>
        </main>
      </div>
    </div>
  )
}

function Page({ section }: { section: string }) {
  switch (section) {
    case 'ask':
      return <Ask />
    case 'search':
      return <Search />
    case 'conversations':
      return <Conversations />
    case 'memories':
      return <Memories />
    case 'memory-review':
      return <MemoryReview />
    case 'ingest':
      return <Ingest />
    case 'generate':
      return <Generate />
    case 'library':
      return <Library />
    case 'mindmap':
      return <MindMap />
    case 'evaluation':
      return <Evaluation />
    case 'retrieval':
      return <Retrieval />
    case 'activity':
      return <Activity />
    case 'diagnostics':
      return <Diagnostics />
    case 'configuration':
      return <Configuration />
    case 'storage':
      return <Storage />
    case 'dashboard':
      return <Dashboard />
    default:
      return (
        <div className="rounded-card border border-border bg-surface px-5 py-8">
          <p className="text-sm font-medium text-text">This view is not available in V1.</p>
          <p className="mt-2">
            <NotAvailable />
          </p>
        </div>
      )
  }
}
