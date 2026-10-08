import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * Spatial mind-map rendering for generated AI Mind Map artifacts.
 *
 * Consumes the existing parsed artifact shape (nodes with id/label and
 * optional description/key_points, edges with source/target/relationship)
 * without changing it: hierarchy is derived inside this visualization only.
 * Layout is a deterministic layered tree from the root with every edge —
 * including cross-links — drawn, so non-tree relationships stay visible.
 * All motion is direct manipulation (no animated transitions), which keeps
 * `prefers-reduced-motion` satisfied while dragging still works.
 */

export interface ArtifactMindMapNode {
  id: string
  label: string
  node_type?: string
  source?: string
  description?: string
  key_points?: string[]
}

export interface ArtifactMindMapEdge {
  source_id: string
  target_id: string
  relationship?: string
}

interface Point {
  x: number
  y: number
}

const TIER_SIZE: Record<number, { w: number; h: number }> = {
  0: { w: 210, h: 68 },
  1: { w: 174, h: 58 },
}

function tierSize(depth: number): { w: number; h: number } {
  return TIER_SIZE[depth] ?? { w: 152, h: 52 }
}

const LAYER_GAP_Y = 150
const LEAF_GAP_X = 190

function truncate(label: string, max = 26): string {
  const clean = label.replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max)}…` : clean
}

interface PlacedNode extends ArtifactMindMapNode {
  x: number
  y: number
  depth: number
}

/** Layered layout: root top-center, children spread beneath their parent. */
function layoutTree(
  nodes: ArtifactMindMapNode[],
  edges: ArtifactMindMapEdge[],
  rootId: string,
): PlacedNode[] {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const children = new Map<string, string[]>()
  const hasParent = new Set<string>()
  const orderedEdges = [...edges].sort((a, b) =>
    a.source_id === b.source_id
      ? a.target_id < b.target_id
        ? -1
        : 1
      : a.source_id < b.source_id
        ? -1
        : 1,
  )
  for (const edge of orderedEdges) {
    if (!byId.has(edge.source_id) || !byId.has(edge.target_id)) continue
    if (edge.source_id === edge.target_id) continue
    const list = children.get(edge.source_id) ?? []
    if (!list.includes(edge.target_id)) {
      list.push(edge.target_id)
      children.set(edge.source_id, list)
      hasParent.add(edge.target_id)
    }
  }
  // Depth-first placement keeps each subtree contiguous; a node already
  // placed (cross-link target) is not moved, so cross-links stay visible
  // without duplicating nodes.
  const placed = new Map<string, { x: number; depth: number }>()
  const inProgress = new Set<string>()
  let cursor = 0
  function visit(id: string, depth: number): number {
    const known = placed.get(id)
    if (known !== undefined) return known.x
    if (inProgress.has(id)) {
      // Back edge of a cycle: reserve a slot so recursion terminates; the
      // outer frame re-centers over the final positions.
      const x = cursor
      cursor += LEAF_GAP_X
      placed.set(id, { x, depth })
      return x
    }
    inProgress.add(id)
    const kids = (children.get(id) ?? []).filter((child) => child !== id)
    let x: number
    if (kids.length === 0) {
      x = cursor
      cursor += LEAF_GAP_X
    } else {
      const positions = kids.map((child) => visit(child, depth + 1))
      x = (Math.min(...positions) + Math.max(...positions)) / 2
    }
    inProgress.delete(id)
    placed.set(id, { x, depth })
    return x
  }
  visit(rootId, 0)
  // Nodes unreachable from the root (separate components) form their own row.
  const orphans = nodes.map((node) => node.id).filter((id) => !placed.has(id)).sort()
  for (const id of orphans) {
    const x = cursor
    cursor += LEAF_GAP_X
    placed.set(id, { x, depth: 1 })
  }
  const minX = Math.min(...[...placed.values()].map((point) => point.x))
  return nodes.map((node) => {
    const point = placed.get(node.id) ?? { x: 0, depth: 1 }
    return { ...node, x: point.x - minX, y: point.depth * LAYER_GAP_Y, depth: point.depth }
  })
}

const controlClass =
  'min-h-[44px] min-w-[44px] rounded-md border border-border bg-surface px-3.5 py-2 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft'

export function MindMapCanvas({
  title,
  nodes,
  edges,
  rootId,
}: {
  title?: string
  nodes: ArtifactMindMapNode[]
  edges: ArtifactMindMapEdge[]
  rootId?: string
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [size, setSize] = useState({ w: 800, h: 480 })
  const [view, setView] = useState({ x: 400, y: 40, k: 0.85 })
  const [dragOffsets, setDragOffsets] = useState<Record<string, { dx: number; dy: number }>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoverEdge, setHoverEdge] = useState<string | null>(null)
  const gesture = useRef({
    mode: 'none' as 'none' | 'pan' | 'node' | 'pinch',
    nodeId: null as string | null,
    nodeStart: null as Point | null,
    lastX: 0,
    lastY: 0,
    moved: false,
    pointers: new Map<number, Point>(),
    pinchDistance: 0,
  })

  const deduped = useMemo(() => {
    const seen = new Set<string>()
    return nodes.filter((node) => {
      if (!node.id || seen.has(node.id)) return false
      seen.add(node.id)
      return true
    })
  }, [nodes])
  const root = rootId !== undefined && deduped.some((node) => node.id === rootId)
    ? rootId
    : (deduped[0]?.id ?? '')
  const placed = useMemo(() => layoutTree(deduped, edges, root), [deduped, edges, root])
  const byId = useMemo(() => new Map(placed.map((node) => [node.id, node])), [placed])
  const validEdges = useMemo(
    () =>
      edges
        .map((edge, i) => ({ ...edge, key: `${edge.source_id}→${edge.target_id}→${edge.relationship ?? ''}#${i}` }))
        .filter((edge) => byId.has(edge.source_id) && byId.has(edge.target_id)),
    [edges, byId],
  )

  function positionOf(id: string): Point {
    const node = byId.get(id)
    const base = node ? { x: node.x, y: node.y } : { x: 0, y: 0 }
    const offset = dragOffsets[id]
    return offset ? { x: base.x + offset.dx, y: base.y + offset.dy } : base
  }

  function fitView() {
    if (placed.length === 0) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const node of placed) {
      const point = positionOf(node.id)
      const size = tierSize(node.depth)
      minX = Math.min(minX, point.x - size.w / 2)
      maxX = Math.max(maxX, point.x + size.w / 2)
      minY = Math.min(minY, point.y - size.h / 2)
      maxY = Math.max(maxY, point.y + size.h / 2)
    }
    const padding = 50
    const k = Math.min(
      1.4,
      Math.max(0.2, Math.min(size.w / (maxX - minX + padding * 2), size.h / (maxY - minY + padding * 2))),
    )
    setView({
      k,
      x: size.w / 2 - ((minX + maxX) / 2) * k,
      y: 24 - minY * k,
    })
  }

  function resetView() {
    setDragOffsets({})
    setSelectedId(null)
    fitView()
  }

  const fittedFor = useRef('')
  useEffect(() => {
    const key = `${root}:${placed.length}`
    if (fittedFor.current !== key) {
      fittedFor.current = key
      fitView()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, placed.length])

  useEffect(() => {
    const element = wrapRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      setSize({ w: Math.max(rect.width, 200), h: Math.max(rect.height, 200) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const svg = svgRef.current
    if (svg === null) return
    function onWheel(event: WheelEvent) {
      event.preventDefault()
      const target = event.currentTarget as SVGSVGElement | null
      const rect = target?.getBoundingClientRect()
      if (!rect) return
      const cursorX = event.clientX - rect.left
      const cursorY = event.clientY - rect.top
      setView((prev) => {
        const next = Math.min(2.5, Math.max(0.2, prev.k * Math.pow(1.0015, -event.deltaY)))
        return {
          k: next,
          x: cursorX - ((cursorX - prev.x) * next) / prev.k,
          y: cursorY - ((cursorY - prev.y) * next) / prev.k,
        }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  function toWorld(clientX: number, clientY: number): Point {
    const rect = svgRef.current?.getBoundingClientRect()
    const left = rect?.left ?? 0
    const top = rect?.top ?? 0
    return { x: (clientX - left - view.x) / view.k, y: (clientY - top - view.y) / view.k }
  }

  function trackPointer(event: React.PointerEvent) {
    gesture.current.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  }

  function beginPinch(): boolean {
    if (gesture.current.pointers.size !== 2) return false
    const [a, b] = [...gesture.current.pointers.values()]
    gesture.current.mode = 'pinch'
    gesture.current.pinchDistance = Math.hypot(a.x - b.x, a.y - b.y)
    return true
  }

  function onBackgroundPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    trackPointer(event)
    if (beginPinch()) return
    gesture.current.mode = 'pan'
    gesture.current.lastX = event.clientX
    gesture.current.lastY = event.clientY
    gesture.current.moved = false
  }

  function onNodePointerDown(event: React.PointerEvent<SVGGElement>, id: string) {
    event.stopPropagation()
    if (event.pointerType === 'mouse' && event.button !== 0) return
    trackPointer(event)
    if (beginPinch()) return
    const world = toWorld(event.clientX, event.clientY)
    const point = positionOf(id)
    gesture.current.mode = 'node'
    gesture.current.nodeId = id
    gesture.current.nodeStart = { x: world.x - point.x, y: world.y - point.y }
    gesture.current.moved = false
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (gesture.current.pointers.has(event.pointerId)) trackPointer(event)
    if (gesture.current.mode === 'pinch' && gesture.current.pointers.size >= 2) {
      const [a, b] = [...gesture.current.pointers.values()]
      const distance = Math.hypot(a.x - b.x, a.y - b.y)
      if (gesture.current.pinchDistance > 0) {
        const factor = distance / gesture.current.pinchDistance
        const rect = svgRef.current?.getBoundingClientRect()
        const cursorX = (a.x + b.x) / 2 - (rect?.left ?? 0)
        const cursorY = (a.y + b.y) / 2 - (rect?.top ?? 0)
        setView((prev) => {
          const next = Math.min(2.5, Math.max(0.2, prev.k * factor))
          return {
            k: next,
            x: cursorX - ((cursorX - prev.x) * next) / prev.k,
            y: cursorY - ((cursorY - prev.y) * next) / prev.k,
          }
        })
      }
      gesture.current.pinchDistance = distance
      gesture.current.moved = true
      return
    }
    if (gesture.current.mode === 'pan') {
      const dx = event.clientX - gesture.current.lastX
      const dy = event.clientY - gesture.current.lastY
      if (dx !== 0 || dy !== 0) gesture.current.moved = true
      gesture.current.lastX = event.clientX
      gesture.current.lastY = event.clientY
      setView((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }))
    } else if (gesture.current.mode === 'node' && gesture.current.nodeId !== null) {
      const nodeId = gesture.current.nodeId
      const world = toWorld(event.clientX, event.clientY)
      const start = gesture.current.nodeStart ?? world
      const offset = { dx: world.x - start.x, dy: world.y - start.y }
      if (Math.abs(offset.dx) + Math.abs(offset.dy) > 4 / view.k) gesture.current.moved = true
      setDragOffsets((prev) => ({ ...prev, [nodeId]: offset }))
    }
  }

  function endGesture(event: React.PointerEvent<SVGSVGElement>) {
    gesture.current.pointers.delete(event.pointerId)
    if (gesture.current.pointers.size === 0) {
      gesture.current.mode = 'none'
      gesture.current.nodeId = null
      gesture.current.nodeStart = null
    } else if (gesture.current.mode === 'pinch') {
      gesture.current.mode = 'none'
    }
  }

  function onNodeClick(event: React.MouseEvent, id: string) {
    event.stopPropagation()
    if (gesture.current.moved) {
      gesture.current.moved = false
      return
    }
    setSelectedId((current) => (current === id ? null : id))
  }

  function onNodeKeyDown(event: React.KeyboardEvent<SVGGElement>, id: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setSelectedId((current) => (current === id ? null : id))
    }
  }

  const selected = selectedId !== null ? (byId.get(selectedId) ?? null) : null
  const selectedRelations = selected
    ? validEdges.filter(
        (edge) => edge.source_id === selected.id || edge.target_id === selected.id,
      )
    : []

  if (deduped.length === 0) {
    return (
      <p className="text-[13px] text-text-muted">
        0 nodes · {edges.length} edges
      </p>
    )
  }

  return (
    <div>
      <div
        ref={wrapRef}
        className="relative min-h-[420px] w-full overflow-hidden rounded-card border border-border bg-bg"
        style={{ height: '60vh' }}
      >
        <svg
          ref={svgRef}
          role="application"
          aria-label={`Mind map of ${title ?? 'generated topics'}. Drag nodes to move them, drag the background to pan, scroll to zoom.`}
          className="block h-full w-full cursor-grab touch-pan-y active:cursor-grabbing"
          onPointerDown={onBackgroundPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endGesture}
          onPointerCancel={endGesture}
          onClick={() => {
            if (!gesture.current.moved) setSelectedId(null)
            gesture.current.moved = false
          }}
        >
          <defs>
            <pattern id="pam-mindmap-dots" width="28" height="28" patternUnits="userSpaceOnUse">
              <circle cx="1.5" cy="1.5" r="1.5" fill="var(--color-border)" opacity="0.55" />
            </pattern>
            <marker id="pam-mm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--color-border-strong)" strokeWidth="1.5" />
            </marker>
            <marker id="pam-mm-arrow-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
            </marker>
          </defs>
          <rect x="-100000" y="-100000" width="200000" height="200000" fill="url(#pam-mindmap-dots)" />
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {validEdges.map((edge) => {
              const from = positionOf(edge.source_id)
              const to = positionOf(edge.target_id)
              const active = edge.key === hoverEdge
              const midX = (from.x + to.x) / 2
              const midY = (from.y + to.y) / 2
              return (
                <g key={edge.key}>
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={active ? 'var(--color-accent)' : 'var(--color-border-strong)'}
                    strokeWidth={active ? 2 : 1.25}
                    markerEnd={active ? 'url(#pam-mm-arrow-accent)' : 'url(#pam-mm-arrow)'}
                  />
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke="transparent"
                    strokeWidth={14}
                    style={{ cursor: 'pointer' }}
                    onClick={(event) => {
                      event.stopPropagation()
                      setHoverEdge((current) => (current === edge.key ? null : edge.key))
                    }}
                    onPointerEnter={() => setHoverEdge(edge.key)}
                    onPointerLeave={() => setHoverEdge((current) => (current === edge.key ? null : current))}
                  >
                    <title>{edge.relationship || 'related'}</title>
                  </line>
                  {active && edge.relationship ? (
                    <text
                      x={midX}
                      y={midY - 8}
                      textAnchor="middle"
                      fontSize={11}
                      fill="var(--color-text-muted)"
                      fontFamily="ui-monospace, monospace"
                    >
                      {edge.relationship}
                    </text>
                  ) : null}
                </g>
              )
            })}
            {placed.map((node) => {
              const point = positionOf(node.id)
              const size = tierSize(node.depth)
              const isSelected = node.id === selectedId
              const isRoot = node.id === root
              return (
                <g
                  key={node.id}
                  transform={`translate(${point.x},${point.y})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${node.label}${node.node_type ? `, ${node.node_type}` : ''}${isRoot ? ', central topic' : ''}`}
                  onPointerDown={(event) => onNodePointerDown(event, node.id)}
                  onClick={(event) => onNodeClick(event, node.id)}
                  onKeyDown={(event) => onNodeKeyDown(event, node.id)}
                  style={{ cursor: 'grab' }}
                >
                  <title>
                    {`${node.label}${node.description ? ` — ${node.description}` : ''}`}
                  </title>
                  <rect
                    x={-size.w / 2}
                    y={-size.h / 2}
                    width={size.w}
                    height={size.h}
                    rx={12}
                    fill={isRoot ? 'var(--color-accent-dim)' : 'var(--color-surface)'}
                    stroke={isSelected ? 'var(--color-accent)' : 'var(--color-border-strong)'}
                    strokeWidth={isSelected || isRoot ? 2 : 1.25}
                  />
                  <text
                    x={0}
                    y={node.description ? -4 : 5}
                    textAnchor="middle"
                    fontSize={isRoot ? 15 : 13}
                    fontWeight={isRoot || node.depth === 1 ? 600 : 500}
                    fill="var(--color-text)"
                  >
                    {truncate(node.label, isRoot ? 30 : 24)}
                  </text>
                  {node.node_type ? (
                    <text
                      x={0}
                      y={node.description ? 26 : 20}
                      textAnchor="middle"
                      fontSize={10}
                      fill="var(--color-text-faint)"
                      fontFamily="ui-monospace, monospace"
                    >
                      {truncate(node.node_type, 22)}
                    </text>
                  ) : null}
                </g>
              )
            })}
          </g>
        </svg>
        <div className="absolute right-3 bottom-3 flex gap-1.5">
          <button type="button" aria-label="Zoom out" title="Zoom out" onClick={() => setView((prev) => ({ ...prev, k: Math.max(0.2, prev.k / 1.25) }))} className={controlClass}>
            −
          </button>
          <button type="button" aria-label="Zoom in" title="Zoom in" onClick={() => setView((prev) => ({ ...prev, k: Math.min(2.5, prev.k * 1.25) }))} className={controlClass}>
            +
          </button>
          <button type="button" aria-label="Fit graph" title="Fit graph" onClick={fitView} className={controlClass}>
            Fit
          </button>
          <button type="button" aria-label="Reset graph" title="Reset graph" onClick={resetView} className={controlClass}>
            Reset
          </button>
        </div>
      </div>
      {selected !== null ? (
        <div className="mt-3 rounded-md border border-border bg-surface px-4 py-3">
          <p className="font-display text-[17px] leading-snug text-text">{selected.label}</p>
          <p className="mt-0.5 font-mono text-[11px] text-text-muted">
            {selected.node_type || 'concept'}
            {selected.source ? ` · ${selected.source}` : null}
          </p>
          {selected.description ? (
            <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">{selected.description}</p>
          ) : null}
          {selected.key_points && selected.key_points.length > 0 ? (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[13px] text-text-muted">
              {selected.key_points.map((point, i) => (
                <li key={`${selected.id}-point-${i}`}>{point}</li>
              ))}
            </ul>
          ) : null}
          {selectedRelations.length > 0 ? (
            <p className="mt-1.5 font-mono text-[11px] text-text-faint">
              {selectedRelations
                .map((edge) =>
                  edge.source_id === selected.id
                    ? `${edge.relationship || 'related to'} → ${byId.get(edge.target_id)?.label ?? edge.target_id}`
                    : `← ${edge.relationship || 'related to'} ${byId.get(edge.source_id)?.label ?? edge.source_id}`,
                )
                .join(' · ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
