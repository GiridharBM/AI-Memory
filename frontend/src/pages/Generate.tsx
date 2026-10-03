import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import { AsyncBoundary, Card, CardHeader, EmptyState } from '../components/common/Card'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import { useJob } from '../lib/jobs'
import { navigate } from '../lib/router'
import type { ArtifactSummary, GenerationTask } from '../lib/types'

const TASKS: { value: GenerationTask; label: string }[] = [
  { value: 'flashcards', label: 'Flashcards' },
  { value: 'quiz', label: 'Quiz' },
  { value: 'report', label: 'Report' },
  { value: 'ppt', label: 'Presentation' },
]

const inputClass =
  'w-full rounded-md border border-border bg-bg px-3 py-2 text-[13px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none'

const labelClass =
  'mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-text-faint'

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
}) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      <input
        type="number"
        className={inputClass}
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      <input
        type="text"
        className={inputClass}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      <select
        className={inputClass}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

function CheckField({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2.5 text-[13px] text-text">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 accent-accent"
      />
      {label}
    </label>
  )
}

export function Generate() {
  const [task, setTask] = useState<GenerationTask>('flashcards')
  const [scopeKind, setScopeKind] = useState<'all' | 'documents'>('all')
  const [sources, setSources] = useState('')
  const [count, setCount] = useState(5)
  const [difficulty, setDifficulty] = useState('intermediate')
  const [optionsPerQuestion, setOptionsPerQuestion] = useState(4)
  const [explanation, setExplanation] = useState(true)
  const [title, setTitle] = useState('')
  const [sectionCount, setSectionCount] = useState(5)
  const [slideCount, setSlideCount] = useState(5)
  const [detailLevel, setDetailLevel] = useState('standard')
  const [speakerNotes, setSpeakerNotes] = useState(true)
  const [query, setQuery] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function buildConfig(): Record<string, string | number | boolean | null> {
    const config: Record<string, string | number | boolean | null> = {}
    if (task === 'flashcards') {
      config.count = count
      config.difficulty = difficulty
    } else if (task === 'quiz') {
      config.count = count
      config.difficulty = difficulty
      config.question_type = 'mcq'
      config.options_per_question = optionsPerQuestion
      config.explanation = explanation
    } else if (task === 'report') {
      if (title.trim()) config.title = title.trim()
      config.section_count = sectionCount
      config.detail_level = detailLevel
    } else {
      if (title.trim()) config.title = title.trim()
      config.slide_count = slideCount
      config.detail_level = detailLevel
      config.theme = 'default'
      config.speaker_notes = speakerNotes
    }
    if (query.trim()) config.query = query.trim()
    return config
  }

  function buildScope(): { kind: 'all' } | { kind: 'documents'; source_ids: string[] } {
    if (scopeKind === 'documents') {
      const ids = sources
        .split(',')
        .map((part) => part.trim())
        .filter((part) => part.length > 0)
      return { kind: 'documents', source_ids: ids }
    }
    return { kind: 'all' }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setSubmitError(null)
    setJobId(null)
    try {
      const created = await api.createGeneration({
        task_type: task,
        memory_scope: buildScope(),
        config: buildConfig(),
      })
      setJobId(created.job_id)
    } catch (cause) {
      setSubmitError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Generate"
        subtitle="Create study material from PAM's shared memory."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader title="Request" subtitle="Task, memory scope, and configuration" />
          <form onSubmit={submit} className="space-y-5 px-5 py-5">
            <div>
              <span className={labelClass}>Task</span>
              <div className="flex flex-wrap gap-2">
                {TASKS.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setTask(item.value)}
                    aria-pressed={task === item.value}
                    className={`rounded-md border px-3.5 py-2 text-[13px] font-medium transition-colors ${
                      task === item.value
                        ? 'border-accent bg-accent-dim text-accent-soft'
                        : 'border-border text-text-muted hover:border-accent/50 hover:text-text'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className={labelClass}>Memory scope</span>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ['all', 'All memory'],
                    ['documents', 'Documents'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setScopeKind(value)}
                    aria-pressed={scopeKind === value}
                    className={`rounded-md border px-3.5 py-2 text-[13px] font-medium transition-colors ${
                      scopeKind === value
                        ? 'border-accent bg-accent-dim text-accent-soft'
                        : 'border-border text-text-muted hover:border-accent/50 hover:text-text'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {scopeKind === 'documents' ? (
                <div className="mt-3">
                  <TextField
                    label="Source identifiers (comma-separated)"
                    value={sources}
                    onChange={setSources}
                    placeholder="a.md, b.md"
                  />
                </div>
              ) : null}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {(task === 'flashcards' || task === 'quiz') && (
                <>
                  <NumberField label="Count" value={count} onChange={setCount} min={1} max={15} />
                  <SelectField
                    label="Difficulty"
                    value={difficulty}
                    options={['beginner', 'intermediate', 'advanced']}
                    onChange={setDifficulty}
                  />
                </>
              )}
              {task === 'quiz' && (
                <>
                  <NumberField
                    label="Options per question"
                    value={optionsPerQuestion}
                    onChange={setOptionsPerQuestion}
                    min={2}
                    max={6}
                  />
                  <div className="flex items-end pb-2">
                    <CheckField
                      label="Include explanations"
                      checked={explanation}
                      onChange={setExplanation}
                    />
                  </div>
                </>
              )}
              {(task === 'report' || task === 'ppt') && (
                <>
                  <TextField label="Title (optional)" value={title} onChange={setTitle} />
                  <SelectField
                    label="Detail level"
                    value={detailLevel}
                    options={['brief', 'standard', 'detailed']}
                    onChange={setDetailLevel}
                  />
                </>
              )}
              {task === 'report' && (
                <NumberField
                  label="Sections"
                  value={sectionCount}
                  onChange={setSectionCount}
                  min={1}
                  max={12}
                />
              )}
              {task === 'ppt' && (
                <>
                  <NumberField
                    label="Slides"
                    value={slideCount}
                    onChange={setSlideCount}
                    min={1}
                    max={20}
                  />
                  <div className="flex items-end pb-2">
                    <CheckField
                      label="Speaker notes"
                      checked={speakerNotes}
                      onChange={setSpeakerNotes}
                    />
                  </div>
                </>
              )}
            </div>

            <TextField
              label="Topic or query (optional)"
              value={query}
              onChange={setQuery}
              placeholder="e.g. retrieval pipelines"
            />

            {submitError ? (
              <p role="alert" className="text-[13px] text-danger">
                {submitError}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="rounded-md border border-accent/40 bg-accent-dim px-4 py-2 text-[13px] font-medium text-accent-soft transition-colors hover:border-accent hover:bg-accent/20 disabled:opacity-50"
            >
              {submitting ? 'Submitting…' : 'Generate'}
            </button>
          </form>
        </Card>

        {jobId !== null ? <JobProgress jobId={jobId} /> : null}
      </div>
    </>
  )
}

function JobProgress({ jobId }: { jobId: string }) {
  const { job, loading, error, cancel, cancelling } = useJob(jobId)

  return (
    <Card>
      <CardHeader title="Job" subtitle={jobId} />
      <div className="space-y-4 px-5 py-5">
        {loading && job === null ? (
          <p className="text-[13px] text-text-muted">Starting…</p>
        ) : null}
        {error ? (
          <p role="alert" className="text-[13px] text-danger">
            {error}
          </p>
        ) : null}
        {job ? (
          <>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px]">
              <span>
                Status: <strong className="font-medium text-text">{job.status}</strong>
              </span>
              <span className="text-text-muted">
                {job.progress}% · {job.stage || '—'}
              </span>
              {job.message ? <span className="text-text-faint">{job.message}</span> : null}
            </div>
            <div
              role="progressbar"
              aria-valuenow={job.progress}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-2 overflow-hidden rounded-full bg-elevated"
            >
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-500"
                style={{ width: `${job.progress}%` }}
              />
            </div>
            {job.status === 'failed' && job.error ? (
              <p role="alert" className="font-mono text-xs break-words text-danger">
                {job.error}
              </p>
            ) : null}
            {job.status === 'cancelled' ? (
              <p className="text-[13px] text-text-muted">Cancelled. No artifact was produced.</p>
            ) : null}
            {(job.status === 'pending' || job.status === 'processing') && (
              <button
                type="button"
                onClick={cancel}
                disabled={cancelling}
                className="rounded-md border border-border-strong bg-elevated px-3 py-1.5 text-xs font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
              >
                {cancelling ? 'Cancelling…' : 'Cancel job'}
              </button>
            )}
            {job.status === 'done' ? <JobArtifact jobId={job.job_id} /> : null}
          </>
        ) : null}
      </div>
    </Card>
  )
}

function JobArtifact({ jobId }: { jobId: string }) {
  const state = useApi(() => api.listArtifacts(), [])

  return (
    <AsyncBoundary state={state}>
      {(data) => {
        const match = data.artifacts.find((item) => item.job_id === jobId)
        if (!match) {
          return <EmptyState title="Artifact not listed yet." hint="Reload to retry." />
        }
        return <ArtifactView artifact={match} compact />
      }}
    </AsyncBoundary>
  )
}

export function ArtifactView({
  artifact,
  compact = false,
}: {
  artifact: ArtifactSummary
  compact?: boolean
}) {
  return (
    <div className={compact ? '' : 'space-y-4'}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
        <strong className="font-medium text-text">{artifact.title}</strong>
        <span className="font-mono text-[11px] uppercase text-text-muted">{artifact.kind}</span>
        <span className="text-text-faint">v{artifact.version}</span>
      </div>
      {artifact.content ? (
        <pre className="overflow-x-auto rounded-md border border-border bg-bg px-4 py-3 font-mono text-xs whitespace-pre-wrap text-text">
          {artifact.content}
        </pre>
      ) : null}
      {artifact.content_ref ? (
        <a
          href={api.artifactContentUrl(artifact.artifact_id)}
          className="inline-block rounded-md border border-accent/40 bg-accent-dim px-3.5 py-2 text-[13px] font-medium text-accent-soft transition-colors hover:border-accent hover:bg-accent/20"
        >
          Download file
        </a>
      ) : null}
      {!compact ? (
        <button
          type="button"
          onClick={() => navigate(`/library/${artifact.artifact_id}`)}
          className="ml-3 text-[13px] text-text-muted transition-colors hover:text-text"
        >
          Open in Library →
        </button>
      ) : null}
    </div>
  )
}
