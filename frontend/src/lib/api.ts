/**
 * Typed client for the local PAM API.
 *
 * Requests go to same-origin `/api`. In development Vite proxies that to the
 * FastAPI process; in production FastAPI serves this bundle. No third-party
 * host is ever contacted.
 */

import type {
  ActivityResponse,
  ArtifactSummary,
  ArtifactVersion,
  ArtifactsResponse,
  AskResponse,
  CapabilitiesResponse,
  ConfigResponse,
  Conversation,
  ConversationAskResponse,
  ConversationMessage,
  ConversationMessagesResponse,
  ConversationsResponse,
  DiagnosticsResponse,
  EvaluationResponse,
  GenerationJob,
  GenerationTask,
  HealthResponse,
  IngestResponse,
  JobsResponse,
  MindMapResponse,
  ProvenanceResponse,
  SearchResponse,
  SourceDetail,
  SourcesResponse,
  StorageResponse,
  SystemResponse,
} from './types'

const BASE = '/api'

/** A failed PAM call. `detail` is the backend's own message, never invented. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json' },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the PAM service. Is it running?')
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // Non-JSON error body; the status line is the best we have.
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as T
}

const post = <T>(path: string, body: unknown): Promise<T> =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  system: () => request<SystemResponse>('/system'),
  health: () => request<HealthResponse>('/health'),
  retrieval: () => request<{ available: boolean; config_error?: string } & SystemResponse['retrieval']>('/retrieval'),
  activity: (limit = 50) => request<ActivityResponse>(`/activity?limit=${limit}`),
  config: () => request<ConfigResponse>('/config'),
  storage: () => request<StorageResponse>('/storage'),
  diagnostics: () => request<DiagnosticsResponse>('/diagnostics'),
  evaluation: () => request<EvaluationResponse>('/evaluation'),
  sources: () => request<SourcesResponse>('/sources'),
  source: (id: string) => request<SourceDetail>(`/sources/${id}`),
  capabilities: () => request<CapabilitiesResponse>('/ingest/capabilities'),
  search: (body: {
    query: string
    top_k?: number
    min_score?: number
    source_type?: string | null
    source?: string | null
  }) => post<SearchResponse>('/search', body),
  ask: (body: { question: string; top_k?: number; min_score?: number }) =>
    post<AskResponse>('/ask', body),
  createConversation: (body: { title?: string }) =>
    post<Conversation>('/conversations', body),
  listConversations: (limit = 50, offset = 0) =>
    request<ConversationsResponse>(`/conversations?limit=${limit}&offset=${offset}`),
  getConversation: (id: string) => request<Conversation>(`/conversations/${id}`),
  appendMessage: (id: string, body: { role: 'user'; content: string }) =>
    post<ConversationMessage>(`/conversations/${id}/messages`, body),
  listMessages: (id: string, limit = 50, offset = 0) =>
    request<ConversationMessagesResponse>(
      `/conversations/${id}/messages?limit=${limit}&offset=${offset}`,
    ),
  archiveConversation: (id: string) =>
    post<Conversation>(`/conversations/${id}/archive`, {}),
  askInConversation: (id: string, body: { question: string; top_k?: number }) =>
    post<ConversationAskResponse>(`/conversations/${id}/ask`, body),
  ingest: (form: FormData) => request<IngestResponse>('/ingest', { method: 'POST', body: form }),
  createGeneration: (body: {
    task_type: GenerationTask
    memory_scope: { kind: 'all' } | { kind: 'documents'; source_ids: string[] }
    config?: Record<string, string | number | boolean | null>
    model_role?: string
  }) => post<GenerationJob>('/generation', body),
  getJob: (id: string) => request<GenerationJob>(`/jobs/${id}`),
  listJobs: () => request<JobsResponse>('/jobs'),
  cancelJob: (id: string) => post<GenerationJob>(`/jobs/${id}/cancel`, {}),
  listArtifacts: () => request<ArtifactsResponse>('/artifacts'),
  getArtifact: (id: string) => request<ArtifactSummary>(`/artifacts/${id}`),
  getArtifactVersions: (id: string) =>
    request<ArtifactVersion>(`/artifacts/${id}/versions`),
  getArtifactProvenance: (id: string) =>
    request<ProvenanceResponse>(`/artifacts/${id}/provenance`),
  getMindMap: (nodeId?: string, depth?: number) => {
    const params = new URLSearchParams()
    if (nodeId !== undefined) params.set('node_id', nodeId)
    if (depth !== undefined) params.set('depth', String(depth))
    const query = params.toString()
    return request<MindMapResponse>(`/mindmap${query ? `?${query}` : ''}`)
  },
  /** Direct download URL for binary artifact content (PPTX). No JSON fetch. */
  artifactContentUrl: (id: string) => `/api/artifacts/${id}/content`,
}
