/**
 * Typed client for the local PAM API.
 *
 * Requests go to same-origin `/api`. In development Vite proxies that to the
 * FastAPI process; in production FastAPI serves this bundle. No third-party
 * host is ever contacted.
 */

import type {
  ActivityResponse,
  AskResponse,
  CapabilitiesResponse,
  ConfigResponse,
  DiagnosticsResponse,
  EvaluationResponse,
  HealthResponse,
  IngestResponse,
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
  ingest: (form: FormData) => request<IngestResponse>('/ingest', { method: 'POST', body: form }),
}
