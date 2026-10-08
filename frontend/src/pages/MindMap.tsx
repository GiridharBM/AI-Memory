import { useEffect, useMemo, useRef, useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, EmptyState } from '../components/common/Card'
import {
  KnowledgeCanvas,
  type CanvasEdge,
  type CanvasNode,
} from '../components/graph/KnowledgeCanvas'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { navigate, useRoute } from '../lib/router'
import type { MindMapNode } from '../lib/types'

function edgeKey(source_id: string, target_id: string, edge_type: string): string {
  return `${source_id}→${target_id}→${edge_type}`
}

function isYouTubeSource(source: string): boolean {
  return /youtu\.?be|youtube\.com/i.test(source)
}

const controlClass =
  'min-h-[44px] rounded-md border border-border bg-surface px-3.5 py-2 text-[13px] font-medium text-text-muted transition-colors hover:border-accent hover:text-text disabled:opacity-40'

export function MindMap() {
  const route = useRoute()
  const routeFocus = route.segments[1] ? decodeURIComponent(route.segments[1]) : null
  const initial = useApi(() => api.getMindMap(), [])
  const [nodes, setNodes] = useState<Map<string, MindMapNode>>(new Map())
  const [edges, setEdges] = useState<Map<string, CanvasEdge>>(new Map())
  const [baseIds, setBaseIds] = useState<Set<string> | null>(null)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null)
  const [expansions, setExpansions] = useState<Map<string, string[]>>(new Map())
  const [expanding, setExpanding] = useState<string | null>(null)
  const [expandError, setExpandError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [centerSignal, setCenterSignal] = useState<{ id: string; n: number } | null>(null)
  const [fitSignal, setFitSignal] = useState(0)
  const [missingNode, setMissingNode] = useState(false)
  const centerCount = useRef(0)
  const loadedRef = useRef(false)

  const nodeList: CanvasNode[] = useMemo(
    () =>
      [...nodes.values()].map((node) => ({
        id: node.id,
        label: node.label,
        node_type: node.node_type,
        source: node.source,
      })),
    [nodes],
  )
  const edgeList: CanvasEdge[] = useMemo(() => [...edges.values()], [edges])

  // Initial bounded projection; a deep-linked node outside the first slice
  // is fetched directly (404 → "Node not found", as before).
  useEffect(() => {
    const data = initial.data
    if (data === null || loadedRef.current) return
    loadedRef.current = true
    const nextNodes = new Map(data.nodes.map((node) => [node.id, node] as const))
    const nextEdges = new Map(
      data.edges.map((edge) => [edgeKey(edge.source_id, edge.target_id, edge.edge_type), { ...edge, key: edgeKey(edge.source_id, edge.target_id, edge.edge_type) }] as const),
    )
    setNodes(nextNodes)
    setEdges(nextEdges)
    setBaseIds(new Set(nextNodes.keys()))
    if (routeFocus !== null && !nextNodes.has(routeFocus)) {
      api
        .getMindMap(routeFocus, 1)
        .then((detail) => {
          setNodes((prev) => {
            const merged = new Map(prev)
            for (const node of detail.nodes) merged.set(node.id, node)
            return merged
          })
          setEdges((prev) => {
            const merged = new Map(prev)
            for (const edge of detail.edges) {
              const key = edgeKey(edge.source_id, edge.target_id, edge.edge_type)
              merged.set(key, { ...edge, key })
            }
            return merged
          })
          setFocusId(routeFocus)
          setSelectedId(routeFocus)
        })
        .catch(() => setMissingNode(true))
    } else {
      setFocusId(routeFocus ?? null)
      setSelectedId(routeFocus)
    }
    setFitSignal((n) => n + 1)
    // Route focus is intentionally read once: later navigation is driven here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.data])

  function focusNode(id: string, updateRoute: boolean) {
    setFocusId(id)
    setSelectedId(id)
    setSelectedEdgeKey(null)
    centerCount.current += 1
    setCenterSignal({ id, n: centerCount.current })
    if (updateRoute) navigate(`/mindmap/${encodeURIComponent(id)}`)
  }

  async function expandNode(id: string) {
    if (expanding !== null) return
    setExpanding(id)
    setExpandError(null)
    try {
      const data = await api.getMindMap(id, 2)
      const freshNodes = data.nodes.filter((node) => !nodes.has(node.id))
      setNodes(new Map([...nodes, ...freshNodes.map((node) => [node.id, node] as const)]))
      setEdges((prev) => {
        const merged = new Map(prev)
        for (const edge of data.edges) {
          const key = edgeKey(edge.source_id, edge.target_id, edge.edge_type)
          if (!merged.has(key)) merged.set(key, { ...edge, key })
        }
        return merged
      })
      const freshIds = freshNodes.map((node) => node.id)
      setExpansions((prev) => {
        const merged = new Map(prev)
        merged.set(id, [...(merged.get(id) ?? []), ...freshIds])
        return merged
      })
    } catch (cause) {
      setExpandError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setExpanding(null)
    }
  }

  function collapseNode(id: string) {
    const remaining = new Map(expansions)
    remaining.delete(id)
    const keep = new Set(baseIds ?? [])
    for (const ids of remaining.values()) for (const nodeId of ids) keep.add(nodeId)
    keep.add(id)
    setExpansions(remaining)
    setNodes((all) => new Map([...all].filter(([nodeId]) => keep.has(nodeId))))
    setEdges((all) => {
      return new Map(
        [...all].filter(
          ([, edge]) => keep.has(edge.source_id) && keep.has(edge.target_id),
        ),
      )
    })
  }

  function resetView() {
    if (expansions.size === 0) return
    const keep = new Set(baseIds ?? [])
    setExpansions(new Map())
    setNodes((all) => new Map([...all].filter(([nodeId]) => keep.has(nodeId))))
    setEdges((all) => {
      return new Map(
        [...all].filter(
          ([, edge]) => keep.has(edge.source_id) && keep.has(edge.target_id),
        ),
      )
    })
    setFitSignal((n) => n + 1)
  }

  // Follow browser back/forward across deep-linked nodes without stealing
  // the viewport: only adopt the route when it actually changed elsewhere.
  const focusRef = useRef<string | null>(null)
  useEffect(() => {
    if (routeFocus !== focusRef.current) {
      focusRef.current = routeFocus
      if (routeFocus !== null && nodes.has(routeFocus)) {
        setFocusId(routeFocus)
        setSelectedId(routeFocus)
        setSelectedEdgeKey(null)
      }
    }
  }, [routeFocus, nodes])

  const selected = selectedId !== null ? (nodes.get(selectedId) ?? null) : null
  const selectedEdge = selectedEdgeKey !== null ? (edges.get(selectedEdgeKey) ?? null) : null
  const incidentEdges = useMemo(() => {
    if (selectedId === null) return []
    return [...edges.values()].filter(
      (edge) => edge.source_id === selectedId || edge.target_id === selectedId,
    )
  }, [edges, selectedId])
  const relatedIds = useMemo(() => {
    if (selectedId === null) return []
    const ids = new Set<string>()
    for (const edge of incidentEdges) {
      ids.add(edge.source_id === selectedId ? edge.target_id : edge.source_id)
    }
    return [...ids].sort().slice(0, 12)
  }, [incidentEdges, selectedId])
  const sameSource = useMemo(() => {
    if (selected === null || !selected.source) return []
    return [...nodes.values()]
      .filter((node) => node.id !== selected.id && node.source === selected.source)
      .sort((a, b) => (a.id < b.id ? -1 : 1))
      .slice(0, 8)
  }, [nodes, selected])
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return [...nodes.values()]
      .filter((node) => node.label.toLowerCase().includes(needle))
      .sort((a, b) => (a.id < b.id ? -1 : 1))
      .slice(0, 8)
  }, [nodes, query])

  const isExpanded = selectedId !== null && expansions.has(selectedId)

  return (
    <>
      <PageHeader
        title="Mind Map"
        subtitle="Explore how your knowledge connects — pan, zoom, and expand."
      />

      <AsyncBoundary state={initial}>
        {() => {
          if (missingNode) {
            return (
              <Card>
                <EmptyState title="Node not found." hint="It may have been removed." />
              </Card>
            )
          }
          if (nodes.size === 0) {
            return (
              <Card>
                <EmptyState
                  title="No graph yet."
                  hint="Ingest documents with entities or concepts to grow the knowledge graph."
                />
              </Card>
            )
          }
          return (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search knowledge map…"
                  aria-label="Search loaded nodes"
                  className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none sm:max-w-xs"
                />
                <button
                  type="button"
                  onClick={() => setFitSignal((n) => n + 1)}
                  className={controlClass}
                >
                  Fit
                </button>
                <button
                  type="button"
                  onClick={resetView}
                  disabled={expansions.size === 0}
                  className={controlClass}
                >
                  Reset view
                </button>
              </div>
              {query.trim() ? (
                <Card>
                  <div className="px-5 py-3">
                    {matches.length === 0 ? (
                      <p className="text-[13px] text-text-muted">
                        No loaded nodes match — try expanding the graph first.
                      </p>
                    ) : (
                      <ul className="divide-y divide-border">
                        {matches.map((node) => (
                          <li key={node.id}>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedId(node.id)
                                setSelectedEdgeKey(null)
                                centerCount.current += 1
                                setCenterSignal({ id: node.id, n: centerCount.current })
                              }}
                              className="flex w-full items-center gap-3 px-1 py-2 text-left"
                            >
                              <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-text">
                                {node.label}
                              </span>
                              <span className="shrink-0 font-mono text-[11px] text-text-faint">
                                {node.node_type}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </Card>
              ) : null}
              <div className="relative">
                <KnowledgeCanvas
                  nodes={nodeList}
                  edges={edgeList}
                  focusId={focusId}
                  selectedId={selectedId}
                  selectedEdgeKey={selectedEdgeKey}
                  highlightSource={selected?.source ?? null}
                  centerSignal={centerSignal}
                  fitSignal={fitSignal}
                  onSelectNode={(id) => {
                    setSelectedId(id)
                    if (id !== null) setSelectedEdgeKey(null)
                  }}
                  onSelectEdge={(key) => {
                    setSelectedEdgeKey(key)
                    if (key !== null) setSelectedId(null)
                  }}
                />
                {selected !== null || selectedEdge !== null ? (
                  <div className="absolute top-3 right-3 bottom-3 w-72 max-w-[85%] overflow-y-auto rounded-md border border-border bg-surface px-4 py-4 shadow-lg">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
                        Inspector
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(null)
                          setSelectedEdgeKey(null)
                        }}
                        aria-label="Close inspector"
                        className="text-[13px] text-text-muted hover:text-text"
                      >
                        ✕
                      </button>
                    </div>
                    {selected !== null ? (
                      <div className="mt-2">
                        <p className="font-display text-[17px] leading-snug text-text">
                          {selected.label}
                        </p>
                        <p className="mt-1 font-mono text-[11px] text-text-muted">
                          {selected.node_type}
                          {isYouTubeSource(selected.source) ? ' · ▶ YouTube source' : null}
                        </p>
                        {selected.source ? (
                          <p className="mt-1 truncate font-mono text-[11px] text-text-faint" title={selected.source}>
                            {selected.source}
                          </p>
                        ) : null}
                        <p className="mt-2 text-[13px] text-text-muted">
                          {incidentEdges.length} relationship{incidentEdges.length === 1 ? '' : 's'}
                          {sameSource.length > 0 ? ` · ${sameSource.length} from the same source` : null}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => focusNode(selected.id, true)}
                            className={controlClass}
                          >
                            Focus
                          </button>
                          {isExpanded ? (
                            <button
                              type="button"
                              onClick={() => collapseNode(selected.id)}
                              className={controlClass}
                            >
                              Collapse
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => expandNode(selected.id)}
                              disabled={expanding !== null}
                              className={controlClass}
                            >
                              {expanding === selected.id ? 'Expanding…' : 'Expand'}
                            </button>
                          )}
                        </div>
                        {expandError ? (
                          <p role="alert" className="mt-2 text-[13px] text-danger">
                            {expandError}
                          </p>
                        ) : null}
                        {relatedIds.length > 0 ? (
                          <div className="mt-4">
                            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
                              Related
                            </p>
                            <ul className="mt-1.5 space-y-1">
                              {relatedIds.map((id) => {
                                const node = nodes.get(id)
                                if (!node) return null
                                return (
                                  <li key={id}>
                                    <button
                                      type="button"
                                      onClick={() => focusNode(id, true)}
                                      className="w-full truncate text-left text-[13px] text-text-muted hover:text-text"
                                    >
                                      {node.label}
                                    </button>
                                  </li>
                                )
                              })}
                            </ul>
                          </div>
                        ) : null}
                        {sameSource.length > 0 ? (
                          <div className="mt-4">
                            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
                              Same source
                            </p>
                            <ul className="mt-1.5 space-y-1">
                              {sameSource.map((node) => (
                                <li key={node.id}>
                                  <button
                                    type="button"
                                    onClick={() => focusNode(node.id, true)}
                                    className="w-full truncate text-left text-[13px] text-text-muted hover:text-text"
                                  >
                                    {node.label}
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    ) : selectedEdge !== null ? (
                      <div className="mt-2">
                        <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
                          Relationship
                        </p>
                        <p className="mt-1 font-display text-[17px] text-text">
                          {selectedEdge.edge_type}
                        </p>
                        <p className="mt-1 text-[13px] text-text-muted">
                          {nodes.get(selectedEdge.source_id)?.label ?? selectedEdge.source_id}
                          {' → '}
                          {nodes.get(selectedEdge.target_id)?.label ?? selectedEdge.target_id}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {nodes.size > 0 ? (
                <p className="font-mono text-[11px] text-text-faint">
                  {nodes.size} nodes · {edges.size} relationships loaded
                  {expansions.size > 0 ? ` · ${expansions.size} expanded` : null}
                </p>
              ) : null}
            </div>
          )
        }}
      </AsyncBoundary>
    </>
  )
}
