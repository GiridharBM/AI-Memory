import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, EmptyState } from '../components/common/Card'
import { api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { navigate, useRoute } from '../lib/router'
import type { MindMapNode } from '../lib/types'

export function MindMap() {
  const route = useRoute()
  const nodeId = route.segments[1] ? decodeURIComponent(route.segments[1]) : undefined

  return nodeId ? <NodeView id={nodeId} /> : <RootView />
}

function RootView() {
  const state = useApi(() => api.getMindMap(), [])

  return (
    <>
      <PageHeader
        title="Mind Map"
        subtitle="Browse PAM's knowledge graph, one neighborhood at a time."
      />

      <AsyncBoundary state={state}>
        {(data) =>
          data.nodes.length === 0 ? (
            <Card>
              <EmptyState
                title="No graph yet."
                hint="Ingest documents with entities or concepts to grow the knowledge graph."
              />
            </Card>
          ) : (
            <NodeList
              nodes={data.nodes}
              edges={data.edges}
              breadcrumb={null}
              title="Graph"
              subtitle={`${data.nodes.length} nodes shown`}
            />
          )
        }
      </AsyncBoundary>
    </>
  )
}

function NodeView({ id }: { id: string }) {
  const state = useApi(() => api.getMindMap(id, 1), [id])

  return (
    <>
      <button
        type="button"
        onClick={() => navigate('/mindmap')}
        className="mb-4 text-[13px] text-text-muted transition-colors hover:text-text"
      >
        ← Mind Map
      </button>

      <AsyncBoundary state={state}>
        {(data) => {
          const root = data.nodes.find((node) => node.id === id)
          if (!root) {
            return (
              <Card>
                <EmptyState title="Node not found." hint="It may have been removed." />
              </Card>
            )
          }
          return (
            <NodeList
              nodes={data.nodes}
              edges={data.edges}
              breadcrumb={root}
              title={root.label}
              subtitle={`${root.node_type} · ${root.source || 'no source'}`}
            />
          )
        }}
      </AsyncBoundary>
    </>
  )
}

function NodeList({
  nodes,
  edges,
  breadcrumb,
  title,
  subtitle,
}: {
  nodes: MindMapNode[]
  edges: { source_id: string; target_id: string; edge_type: string }[]
  breadcrumb: MindMapNode | null
  title: string
  subtitle: string
}) {
  const currentId = breadcrumb?.id ?? null
  const neighbors = currentId
    ? nodes.filter((node) => node.id !== currentId)
    : nodes

  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      {neighbors.length === 0 ? (
        <EmptyState title="No neighbors." hint="This node stands alone in the graph." />
      ) : (
        <ul className="divide-y divide-border">
          {neighbors.map((node) => {
            const relation = currentId
              ? edges.find(
                  (edge) =>
                    (edge.source_id === currentId && edge.target_id === node.id) ||
                    (edge.target_id === currentId && edge.source_id === node.id),
                )
              : undefined
            return (
              <li key={node.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/mindmap/${encodeURIComponent(node.id)}`)}
                  className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors hover:bg-elevated/50"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-text">
                      {node.label}
                    </span>
                    <span className="mt-0.5 block truncate font-mono text-[11px] text-text-faint">
                      {node.source || 'no source'}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[11px] uppercase text-text-muted">
                    {node.node_type}
                  </span>
                  {relation ? (
                    <span className="w-36 shrink-0 truncate text-right font-mono text-[11px] text-text-faint">
                      {relation.edge_type}
                    </span>
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
