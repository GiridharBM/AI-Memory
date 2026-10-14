/**
 * Typed client for the local PAM API.
 *
 * Requests go to same-origin `/api`. In development Vite proxies that to the
 * FastAPI process; in production FastAPI serves this bundle. No third-party
 * host is ever contacted.
 */

import type {
  ActivityResponse,
  ApproveCandidateResponse,
  ArtifactSummary,
  ArtifactVersion,
  ArtifactsResponse,
  AskResponse,
  CandidateListResponse,
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
  MemoryCandidate,
  MemoryCategory,
  MemoryListResponse,
  MemoryProvenanceResponse,
  MemoryRecord,
  MindMapResponse,
  ProvenanceResponse,
  RetrievalFlags,
  SearchResponse,
  SourceDetail,
  SourcesResponse,
  StorageResponse,
  SystemResponse,
} from './types'

const BASE = '/api'

function encodePathSegment(value: string): string {
  if (value === '.' || value === '..' || value.includes('/') || value.includes('\\')) {
    throw new ApiError(0, 'Invalid PAM API request.')
  }
  return encodeURIComponent(value)
}

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
  const url = new URL(`${BASE}${path}`, window.location.origin)
  if (url.origin !== window.location.origin || !url.pathname.startsWith(`${BASE}/`)) {
    throw new ApiError(0, 'Invalid PAM API request.')
  }

  let response: Response
  try {
    response = await fetch(url, {
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
  retrievalFlags: () => request<RetrievalFlags>('/config/retrieval'),
  updateRetrievalFlags: (body: Partial<RetrievalFlags>) =>
    post<RetrievalFlags>('/config/retrieval', body),
  activity: (limit = 50) => request<ActivityResponse>(`/activity?limit=${limit}`),
  config: () => request<ConfigResponse>('/config'),
  storage: () => request<StorageResponse>('/storage'),
  diagnostics: () => request<DiagnosticsResponse>('/diagnostics'),
  evaluation: () => request<EvaluationResponse>('/evaluation'),
  sources: () => request<SourcesResponse>('/sources'),
  source: (id: string) => request<SourceDetail>(`/sources/${encodePathSegment(id)}`),
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
  getConversation: (id: string) =>
    request<Conversation>(`/conversations/${encodePathSegment(id)}`),
  appendMessage: (id: string, body: { role: 'user'; content: string }) =>
    post<ConversationMessage>(`/conversations/${encodePathSegment(id)}/messages`, body),
  listMessages: (id: string, limit = 50, offset = 0) =>
    request<ConversationMessagesResponse>(
      `/conversations/${encodePathSegment(id)}/messages?limit=${limit}&offset=${offset}`,
    ),
  archiveConversation: (id: string) =>
    post<Conversation>(`/conversations/${encodePathSegment(id)}/archive`, {}),
  askInConversation: (id: string, body: { question: string; top_k?: number }) =>
    post<ConversationAskResponse>(`/conversations/${encodePathSegment(id)}/ask`, body),
  extractMemories: (conversationId: string) =>
    post<CandidateListResponse>('/memories/extract', { conversation_id: conversationId }),
  listCandidates: (limit = 50, offset = 0) =>
    request<CandidateListResponse>(`/memories/candidates?limit=${limit}&offset=${offset}`),
  getCandidate: (id: string) =>
    request<MemoryCandidate>(`/memories/candidates/${encodePathSegment(id)}`),
  approveCandidate: (id: string, body: { edited_text?: string }) =>
    post<ApproveCandidateResponse>(
      `/memories/candidates/${encodePathSegment(id)}/approve`,
      body,
    ),
  rejectCandidate: (id: string, body: { reason: string }) =>
    post<MemoryCandidate>(`/memories/candidates/${encodePathSegment(id)}/reject`, body),
  editCandidate: (id: string, body: { edited_text: string }) =>
    post<MemoryCandidate>(`/memories/candidates/${encodePathSegment(id)}/edit`, body),
  listMemories: (limit = 50, offset = 0, logicalId?: string) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (logicalId !== undefined) params.set('logical_id', logicalId)
    return request<MemoryListResponse>(`/memories?${params.toString()}`)
  },
  getMemory: (id: string) =>
    request<MemoryRecord>(`/memories/${encodePathSegment(id)}`),
  supersedeMemory: (
    logicalId: string,
    body: { text: string; category: MemoryCategory; confidence: number },
  ) => post<MemoryRecord>(`/memories/${encodePathSegment(logicalId)}/supersede`, body),
  memoryProvenance: (id: string) =>
    request<MemoryProvenanceResponse>(
      `/memories/${encodePathSegment(id)}/provenance`,
    ),
  ingest: (form: FormData) => request<IngestResponse>('/ingest', { method: 'POST', body: form }),
  createGeneration: (body: {
    task_type: GenerationTask
    memory_scope: { kind: 'all' } | { kind: 'documents'; source_ids: string[] }
    config?: Record<string, string | number | boolean | null>
    model_role?: string
  }) => post<GenerationJob>('/generation', body),
  getJob: (id: string) => request<GenerationJob>(`/jobs/${encodePathSegment(id)}`),
  listJobs: () => request<JobsResponse>('/jobs'),
  cancelJob: (id: string) =>
    post<GenerationJob>(`/jobs/${encodePathSegment(id)}/cancel`, {}),
  listArtifacts: () => request<ArtifactsResponse>('/artifacts'),
  getArtifact: (id: string) =>
    request<ArtifactSummary>(`/artifacts/${encodePathSegment(id)}`),
  getArtifactVersions: (id: string) =>
    request<ArtifactVersion>(`/artifacts/${encodePathSegment(id)}/versions`),
  getArtifactProvenance: (id: string) =>
    request<ProvenanceResponse>(
      `/artifacts/${encodePathSegment(id)}/provenance`,
    ),
  getMindMap: (nodeId?: string, depth?: number) => {
    const params = new URLSearchParams()
    if (nodeId !== undefined) params.set('node_id', nodeId)
    if (depth !== undefined) params.set('depth', String(depth))
    const query = params.toString()
    return request<MindMapResponse>(`/mindmap${query ? `?${query}` : ''}`)
  },
  /** Direct download URL for binary artifact content (PPTX). No JSON fetch. */
  artifactContentUrl: (id: string) =>
    `/api/artifacts/${encodePathSegment(id)}/content`,
}
