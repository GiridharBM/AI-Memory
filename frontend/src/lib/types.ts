/**
 * Response shapes from `app/interfaces/web/`.
 *
 * Every numeric field that PAM may be unable to determine is `number | null`
 * rather than a sentinel. The UI is required to render `null` as "Not
 * available"; there is no fake-data fallback anywhere in this app.
 */

export type HealthStatus = 'ready' | 'unavailable' | 'disabled' | 'unknown'

export interface HealthItem {
  label: string
  value: string | null
  status: HealthStatus
  detail: string | null
}

export interface RetrievalStage {
  id: string
  label: string
  active: boolean
  detail?: string | null
}

export interface RetrievalConfig {
  top_k_default: number
  rrf_k: number
  min_cosine: number
  qa_timeout_seconds: number
  ollama_num_ctx: number
  stages: RetrievalStage[]
}

export interface SystemResponse {
  state: 'healthy' | 'degraded' | 'unknown'
  config_ok: boolean
  config_error: string | null
  metrics: {
    sources: number | null
    chunks: number | null
    ledger_entries: number | null
    processed: number | null
    skipped_duplicates: number | null
    failed: number | null
    queue_waiting: number | null
  }
  health: Record<string, HealthItem>
  retrieval: RetrievalConfig | null
  activity: { available: boolean; total: number | null; latest: string | null } | null
  capabilities?: string
  version?: string | null
  environment?: string
}

export interface HealthResponse {
  state: 'healthy' | 'degraded' | 'unknown'
  config_ok?: boolean
  config_error?: string
  ollama_reachable?: boolean
  ollama_model_present?: boolean | null
  detail?: string
}

export interface SearchHit {
  entry_id: string
  source: string
  source_type: string | null
  text: string
  score: number
  cosine_score: number
  bm25_score: number
  /** null when the reranker is disabled or did not score this hit. */
  rerank_score: number | null
  chunk_index: number
  start_char: number | null
  end_char: number | null
  parent_section: string | null
  metadata: Record<string, string>
}

export interface SearchResponse {
  query: string
  count: number
  filters: Record<string, string> | null
  latency_seconds: number | null
  results: SearchHit[]
}

export interface Citation extends SearchHit {
  number: number
}

export interface AskResponse {
  question: string
  answer: string
  outcome: 'answered' | 'abstained'
  abstention_reason: string | null
  /** "system" = answered from deterministic system facts, no citations. */
  origin: 'retrieval' | 'system'
  model: string | null
  latency_seconds: number | null
  citations: Citation[]
  invalid_citations: number[]
  duplicate_citations: number
  sources: SearchHit[]
  telemetry: {
    answer_length: number
    source_count: number
    citation_count: number
    invalid_citation_count: number
    duplicate_citation_count: number
    answer_has_insufficiency_language: boolean
  } | null
}

export interface SourceSummary {
  id: string
  source: string
  name: string
  type: string | null
  chunks: number
  status: string
  last_ingested: string | null
}

export interface SourcesResponse {
  available: boolean
  config_error?: string
  total: number
  total_chunks: number | null
  by_type: [string, number][]
  sources: SourceSummary[]
}

export interface SourceChunk {
  entry_id: string
  chunk_index: number
  text: string
  start_char: number | null
  end_char: number | null
  metadata: Record<string, string>
}

export interface SourceDetail {
  available: boolean
  id: string
  source: string
  name: string
  type: string | null
  status: string
  last_ingested: string | null
  chunk_count: number
  store_path: string
  chunks_truncated: boolean
  chunks: SourceChunk[]
}

export interface ActivityEvent {
  at: string | null
  status: string
  filename: string | null
  source: string | null
  extension: string | null
  chunks_stored: number | null
  note: string | null
  error_reason: string | null
  embedding_succeeded: boolean | null
  indexing_succeeded: boolean | null
}

export interface ActivityResponse {
  available: boolean
  scope: 'ingestion'
  total?: number
  events: ActivityEvent[]
}

export interface ConfigResponse {
  available: boolean
  config_error?: string
  config: Record<string, unknown> | null
}

export interface StorageResponse {
  available: boolean
  config_error?: string
  vector_store: {
    type: string
    path: string
    exists: boolean
    size_bytes: number | null
    sources: number | null
    chunks: number | null
  }
  knowledge_graph: { path: string; exists: boolean; size_bytes: number | null }
  manifest: { path: string; enabled: boolean; entries: number | null }
  vault: { notes_root: string; notes: number }
  paths: Record<string, string>
}

export interface DiagnosticsResponse {
  available: boolean
  config_error?: string
  environment?: {
    python: string
    platform: string
    pam_version: string | null
    environment: string
    config_file: string
  }
  models?: {
    llm: string
    embeddings: string
    vision: string
    audio: string
    ollama_host: string
    ollama_reachable: boolean
    ollama_model_present: boolean | null
    ollama_detail: string
    ollama_num_ctx: number
  }
  retrieval?: RetrievalConfig & {
    reranker_enabled: boolean
    reranker_model: string
    hyde_enabled: boolean
    answerability_enabled: boolean
  }
  ingestion?: {
    ocr_enabled: boolean
    ocr_engine: string
    ocr_page_limit: number
    metadata_enabled: boolean
    watcher_enabled: boolean
    watcher_extensions: string[]
  }
  storage?: {
    sources: number | null
    chunks: number | null
    directories: { label: string; ok: boolean; detail: string }[]
  }
}

export interface EvaluationResponse {
  available: boolean
  config_error?: string
  results_dir?: string
  artifact_count?: number
  artifacts?: {
    name: string
    size_bytes: number
    modified: number
    kind: string
  }[]
  runtime_metrics_available?: boolean
}

export interface CapabilitiesResponse {
  available: boolean
  config_error?: string
  extensions?: string[]
  extension_count?: number
  url_inputs?: { kind: string; label: string; source_type: string }[]
}

export interface IngestResponse {
  status: 'processed' | 'skipped_duplicate'
  source: string
  source_type?: string
  note_title?: string
  note_path?: string
  created?: boolean
  updated?: boolean
  chunks_stored?: number
  embedding_succeeded?: boolean
  indexing_succeeded?: boolean
  graph_succeeded?: boolean
  graph_warning?: string | null
  message?: string
}

export type GenerationTask = 'flashcards' | 'quiz' | 'report' | 'ppt' | 'image'

export type GenerationJobStatus =
  | 'pending'
  | 'processing'
  | 'validating'
  | 'done'
  | 'failed'
  | 'cancelled'

export interface GenerationJob {
  job_id: string
  task_type: string
  status: GenerationJobStatus
  progress: number
  stage: string
  message: string
  created_at: string
  updated_at: string
  error: string | null
}

export interface JobsResponse {
  jobs: GenerationJob[]
  total: number
}

export interface ArtifactSummary {
  artifact_id: string
  logical_id: string
  kind: string
  title: string
  version: number
  created_at: string
  updated_at: string
  job_id: string
  model_role: string
  metadata: Record<string, string>
  content: string | null
  content_ref: string | null
}

export interface ArtifactsResponse {
  artifacts: ArtifactSummary[]
  total: number
}

export interface ArtifactVersion {
  artifact_id: string
  logical_id: string
  versions: ArtifactSummary[]
}

export interface ProvenanceEntry {
  artifact_id: string
  source_id: string
  role: string
  source_type: string | null
  chunk_id: string | null
  chunk_index: number | null
  start_char: number | null
  end_char: number | null
  kg_node_id: string | null
  quote: string | null
}

export interface ProvenanceResponse {
  artifact_id: string
  records: ProvenanceEntry[]
  total: number
}

export interface MindMapNode {
  id: string
  label: string
  node_type: string
  source: string
}

export interface MindMapEdge {
  source_id: string
  target_id: string
  edge_type: string
}

export interface MindMapResponse {
  available: boolean
  nodes: MindMapNode[]
  edges: MindMapEdge[]
  root: string | null
}
