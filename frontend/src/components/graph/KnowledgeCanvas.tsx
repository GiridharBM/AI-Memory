import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * Interactive spatial canvas over PAM's knowledge graph.
 *
 * A dependency-free SVG implementation chosen deliberately: the mind-map API
 * returns bounded projections (≤100 nodes, depth ≤3), so a small custom canvas
 * covers pan/zoom/drag/select/expand without a graph-library dependency.
 * Nothing here invents graph structure — nodes, edges, and types all come
 * from the API. Node positions derive from a deterministic BFS layout around
 * the focus node; user drags persist per node id and survive data merges.
 */

export interface CanvasNode {
  id: string
  label: string
  node_type: string
  source: string
}

export interface CanvasEdge {
  key: string
  source_id: string
  target_id: string
  edge_type: string
}

interface Point {
  x: number
  y: number
}

interface DragOffset {
  dx: number
  dy: number
}

const MAX_RENDER_NODES = 200
const NODE_W = 150
const NODE_H = 54
const MIN_ZOOM = 0.2
const MAX_ZOOM = 3

const TYPE_GLYPH: Record<string, string> = {
  topic: '●',
  concept: '◆',
  entity: '▲',
  note: '▤',
  definition: '✎',
}

const TYPE_BAR: Record<string, string> = {
  topic: 'bg-accent',
  concept: 'bg-border-strong',
  entity: 'bg-text-muted',
  note: 'bg-text-faint',
  definition: 'bg-text-faint',
}

function truncate(label: string, max = 24): string {
  const clean = label.replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max)}…` : clean
}

function layoutGraph(
  ids: string[],
  adjacency: Map<string, Set<string>>,
  focusId: string | null,
): Map<string, Point> {
  const focus = focusId !== null && ids.includes(focusId) ? focusId : (ids[0] ?? null)
  const layer = new Map<string, number>()
  if (focus !== null) {
    const queue: string[] = [focus]
    layer.set(focus, 0)
    while (queue.length > 0) {
      const current = queue.shift() as string
      const depth = layer.get(current) as number
      const neighbors = [...(adjacency.get(current) ?? [])].sort()
      for (const neighbor of neighbors) {
        if (!layer.has(neighbor)) {
          layer.set(neighbor, depth + 1)
          queue.push(neighbor)
        }
      }
    }
  }
  const byLayer = new Map<number, string[]>()
  for (const id of ids) {
    const depth = layer.get(id) ?? 99
    const group = byLayer.get(depth) ?? []
    group.push(id)
    byLayer.set(depth, group)
  }
  const placed = new Map<string, Point>()
  const orderedLayers = [...byLayer.entries()].sort((a, b) => a[0] - b[0])
  for (const [depth, group] of orderedLayers) {
    const ordered = [...group].sort()
    if (depth === 0) {
      placed.set(ordered[0], { x: 0, y: 0 })
    } else if (depth >= 99) {
      const radius = 760
      ordered.forEach((id, i) => {
        const angle = (2 * Math.PI * i) / Math.max(ordered.length, 1) - Math.PI / 2
        placed.set(id, { x: radius * Math.cos(angle) + 900, y: radius * Math.sin(angle) })
      })
    } else {
      const radius = Math.max(210, (ordered.length * 130) / (2 * Math.PI)) + (depth - 1) * 190
      ordered.forEach((id, i) => {
        const angle = (2 * Math.PI * i) / Math.max(ordered.length, 1) + depth * 0.5 - Math.PI / 2
        placed.set(id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) })
      })
    }
  }
  return placed
}

interface KnowledgeCanvasProps {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
  focusId: string | null
  selectedId: string | null
  selectedEdgeKey: string | null
  highlightSource: string | null
  centerSignal: { id: string; n: number } | null
  fitSignal: number
  onSelectNode: (id: string | null) => void
  onSelectEdge: (key: string | null) => void
}

export function KnowledgeCanvas({
  nodes,
  edges,
  focusId,
  selectedId,
  selectedEdgeKey,
  highlightSource,
  centerSignal,
  fitSignal,
  onSelectNode,
  onSelectEdge,
}: KnowledgeCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [size, setSize] = useState({ w: 800, h: 560 })
  const [view, setView] = useState({ x: 400, y: 280, k: 0.8 })
  const [dragOffsets, setDragOffsets] = useState<Record<string, DragOffset>>({})
  const [hoverEdgeKey, setHoverEdgeKey] = useState<string | null>(null)
  const gesture = useRef({
    mode: 'none' as 'none' | 'pan' | 'node' | 'pinch',
    nodeId: null as string | null,
    nodeStart: null as Point | null,
    view: null as { x: number; y: number; k: number } | null,
    lastX: 0,
    lastY: 0,
    moved: false,
    pointers: new Map<number, Point>(),
    pinchDistance: 0,
  })

  const visible = useMemo(() => {
    const ordered = [...nodes].sort((a, b) => (a.id < b.id ? -1 : 1))
    return ordered.slice(0, MAX_RENDER_NODES)
  }, [nodes])
  const visibleIds = useMemo(() => new Set(visible.map((node) => node.id)), [visible])
  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (edge) => visibleIds.has(edge.source_id) && visibleIds.has(edge.target_id),
      ),
    [edges, visibleIds],
  )
  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>()
    function link(a: string, b: string) {
      const set = map.get(a)
      if (set) set.add(b)
      else map.set(a, new Set([b]))
    }
    for (const edge of visibleEdges) {
      link(edge.source_id, edge.target_id)
      link(edge.target_id, edge.source_id)
    }
    return map
  }, [visibleEdges])

  const layout = useMemo(
    () => layoutGraph(visible.map((node) => node.id), adjacency, focusId),
    // Layout must stay stable while dragging: drag offsets live separately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visible, adjacency, focusId],
  )

  function positionOf(id: string): Point {
    const base = layout.get(id) ?? { x: 0, y: 0 }
    const offset = dragOffsets[id]
    return offset ? { x: base.x + offset.dx, y: base.y + offset.dy } : base
  }

  function fitView() {
    if (visible.length === 0) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const node of visible) {
      const point = positionOf(node.id)
      minX = Math.min(minX, point.x - NODE_W / 2)
      maxX = Math.max(maxX, point.x + NODE_W / 2)
      minY = Math.min(minY, point.y - NODE_H / 2)
      maxY = Math.max(maxY, point.y + NODE_H / 2)
    }
    const padding = 60
    const k = Math.min(
      MAX_ZOOM,
      Math.max(
        MIN_ZOOM,
        Math.min(size.w / (maxX - minX + padding * 2), size.h / (maxY - minY + padding * 2)),
      ),
    )
    setView({
      k,
      x: size.w / 2 - ((minX + maxX) / 2) * k,
      y: size.h / 2 - ((minY + maxY) / 2) * k,
    })
  }

  function centerOn(id: string) {
    const point = positionOf(id)
    setView((prev) => ({
      k: prev.k,
      x: size.w / 2 - point.x * prev.k,
      y: size.h / 2 - point.y * prev.k,
    }))
  }

  const fitSignalRef = useRef(fitSignal)
  useEffect(() => {
    if (fitSignal !== fitSignalRef.current) {
      fitSignalRef.current = fitSignal
      fitView()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitSignal])

  const centerSignalRef = useRef(centerSignal)
  useEffect(() => {
    if (centerSignal !== centerSignalRef.current) {
      centerSignalRef.current = centerSignal
      if (centerSignal !== null && visibleIds.has(centerSignal.id)) {
        centerOn(centerSignal.id)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerSignal])

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
        const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev.k * Math.pow(1.0015, -event.deltaY)))
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
    gesture.current.view = view
    const current = view
    return { x: (clientX - left - current.x) / current.k, y: (clientY - top - current.y) / current.k }
  }

  function trackPointer(event: React.PointerEvent) {
    gesture.current.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  }

  function onBackgroundPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    trackPointer(event)
    if (gesture.current.pointers.size === 2) {
      const [a, b] = [...gesture.current.pointers.values()]
      gesture.current.mode = 'pinch'
      gesture.current.pinchDistance = Math.hypot(a.x - b.x, a.y - b.y)
      return
    }
    gesture.current.mode = 'pan'
    gesture.current.lastX = event.clientX
    gesture.current.lastY = event.clientY
    gesture.current.moved = false
  }

  function onNodePointerDown(event: React.PointerEvent<SVGGElement>, id: string) {
    event.stopPropagation()
    if (event.pointerType === 'mouse' && event.button !== 0) return
    trackPointer(event)
    if (gesture.current.pointers.size === 2) {
      const [a, b] = [...gesture.current.pointers.values()]
      gesture.current.mode = 'pinch'
      gesture.current.pinchDistance = Math.hypot(a.x - b.x, a.y - b.y)
      return
    }
    gesture.current.mode = 'node'
    gesture.current.nodeId = id
    gesture.current.lastX = event.clientX
    gesture.current.lastY = event.clientY
    gesture.current.moved = false
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (gesture.current.pointers.has(event.pointerId)) {
      trackPointer(event)
    }
    if (gesture.current.mode === 'pinch' && gesture.current.pointers.size >= 2) {
      const [a, b] = [...gesture.current.pointers.values()]
      const distance = Math.hypot(a.x - b.x, a.y - b.y)
      if (gesture.current.pinchDistance > 0) {
        const factor = distance / gesture.current.pinchDistance
        const rect = svgRef.current?.getBoundingClientRect()
        const cursorX = (a.x + b.x) / 2 - (rect?.left ?? 0)
        const cursorY = (a.y + b.y) / 2 - (rect?.top ?? 0)
        setView((prev) => {
          const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev.k * factor))
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
      if (Math.abs(dx) + Math.abs(dy) > 0) gesture.current.moved = true
      gesture.current.lastX = event.clientX
      gesture.current.lastY = event.clientY
      setView((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }))
    } else if (gesture.current.mode === 'node' && gesture.current.nodeId !== null) {
      const nodeId = gesture.current.nodeId
      const world = toWorld(event.clientX, event.clientY)
      const base = layout.get(nodeId) ?? { x: 0, y: 0 }
      const start = gesture.current.nodeStart ?? base
      const offset = { dx: world.x - start.x, dy: world.y - start.y }
      if (Math.abs(offset.dx) + Math.abs(offset.dy) > 4 / view.k) {
        gesture.current.moved = true
      }
      setDragOffsets((prev) => ({ ...prev, [nodeId]: offset }))
    }
  }

  function endGesture(event: React.PointerEvent<SVGSVGElement>) {
    gesture.current.pointers.delete(event.pointerId)
    if (gesture.current.pointers.size === 0) {
      gesture.current.mode = 'none'
      gesture.current.nodeId = null
      gesture.current.nodeStart = null
    } else if (gesture.current.pointers.size < 2 && gesture.current.mode === 'pinch') {
      gesture.current.mode = 'none'
    }
  }

  function beginNodeDrag(event: React.PointerEvent<SVGGElement>, id: string) {
    onNodePointerDown(event, id)
    const world = toWorld(event.clientX, event.clientY)
    const point = positionOf(id)
    gesture.current.nodeStart = { x: world.x - point.x, y: world.y - point.y }
  }

  function onNodeClick(event: React.MouseEvent, id: string) {
    event.stopPropagation()
    if (gesture.current.moved) {
      gesture.current.moved = false
      return
    }
    onSelectNode(id)
  }

  function onNodeKeyDown(event: React.KeyboardEvent<SVGGElement>, id: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelectNode(id)
    }
  }

  return (
    <div ref={wrapRef} className="relative h-[70vh] min-h-[480px] w-full overflow-hidden rounded-card border border-border bg-bg">
      <svg
        ref={svgRef}
        role="application"
        aria-label="Knowledge graph canvas. Drag to pan, scroll to zoom, drag nodes to move them."
        className="block h-full w-full cursor-grab touch-pan-y active:cursor-grabbing"
        onPointerDown={onBackgroundPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endGesture}
        onPointerCancel={endGesture}
        onClick={() => {
          if (!gesture.current.moved) {
            onSelectNode(null)
            onSelectEdge(null)
          }
          gesture.current.moved = false
        }}
      >
        <defs>
          <pattern id="pam-canvas-dots" width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.5" fill="var(--color-border)" opacity="0.55" />
          </pattern>
          <marker id="pam-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--color-border-strong)" strokeWidth="1.5" />
          </marker>
          <marker id="pam-arrow-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
          </marker>
        </defs>
        <rect x="-100000" y="-100000" width="200000" height="200000" fill="url(#pam-canvas-dots)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {visibleEdges.map((edge) => {
            const from = positionOf(edge.source_id)
            const to = positionOf(edge.target_id)
            const active = edge.key === selectedEdgeKey || edge.key === hoverEdgeKey
            return (
              <g key={edge.key}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={active ? 'var(--color-accent)' : 'var(--color-border-strong)'}
                  strokeWidth={active ? 2 : 1.25}
                  markerEnd={active ? 'url(#pam-arrow-accent)' : 'url(#pam-arrow)'}
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
                    onSelectEdge(edge.key)
                  }}
                  onPointerEnter={() => setHoverEdgeKey(edge.key)}
                  onPointerLeave={() => setHoverEdgeKey((current) => (current === edge.key ? null : current))}
                >
                  <title>{edge.edge_type}</title>
                </line>
                {active ? (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 8}
                    textAnchor="middle"
                    fontSize={11}
                    fill="var(--color-text-muted)"
                    fontFamily="ui-monospace, monospace"
                  >
                    {edge.edge_type}
                  </text>
                ) : null}
              </g>
            )
          })}
          {visible.map((node) => {
            const point = positionOf(node.id)
            const selected = node.id === selectedId
            const focused = node.id === focusId
            const highlighted = highlightSource !== null && highlightSource !== '' && node.source === highlightSource
            return (
              <g
                key={node.id}
                transform={`translate(${point.x},${point.y})`}
                tabIndex={0}
                role="button"
                aria-label={`${node.label}, ${node.node_type}${node.source ? `, from ${node.source}` : ''}`}
                onPointerDown={(event) => beginNodeDrag(event, node.id)}
                onClick={(event) => onNodeClick(event, node.id)}
                onKeyDown={(event) => onNodeKeyDown(event, node.id)}
                style={{ cursor: 'grab' }}
              >
                <title>{`${node.label} · ${node.node_type}${node.source ? ` · ${node.source}` : ''}`}</title>
                {highlighted ? (
                  <rect x={-NODE_W / 2 - 5} y={-NODE_H / 2 - 5} width={NODE_W + 10} height={NODE_H + 10} rx={14} fill="none" stroke="var(--color-accent)" strokeWidth={1.5} opacity={0.7} />
                ) : null}
                <rect
                  x={-NODE_W / 2}
                  y={-NODE_H / 2}
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  fill="var(--color-surface)"
                  stroke={selected || focused ? 'var(--color-accent)' : 'var(--color-border-strong)'}
                  strokeWidth={selected || focused ? 2 : 1.25}
                  strokeDasharray={focused && !selected ? '5 3' : undefined}
                />
                <rect
                  x={-NODE_W / 2}
                  y={-NODE_H / 2}
                  width={4}
                  height={NODE_H}
                  rx={2}
                  className={TYPE_BAR[node.node_type] ?? 'bg-text-faint'}
                />
                <text x={-NODE_W / 2 + 14} y={-2} fontSize={13} fontWeight={600} fill="var(--color-text)">
                  {(TYPE_GLYPH[node.node_type] ?? '○') + ' ' + truncate(node.label, 19)}
                </text>
                <text x={-NODE_W / 2 + 14} y={16} fontSize={10} fill="var(--color-text-faint)" fontFamily="ui-monospace, monospace">
                  {truncate(node.node_type, 18)}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      {nodes.length > MAX_RENDER_NODES ? (
        <p className="absolute top-3 left-3 rounded-md border border-border bg-surface px-3 py-1.5 font-mono text-[11px] text-text-muted">
          Showing {MAX_RENDER_NODES} of {nodes.length} nodes — search or expand to explore more.
        </p>
      ) : null}
    </div>
  )
}
