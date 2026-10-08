import { useState } from 'react'

import { PageHeader } from '../components/dashboard/MetricCard'
import {
  AsyncBoundary,
  Card,
  CardHeader,
  EmptyState,
  StatusBadge,
} from '../components/common/Card'
import { ApiError, api } from '../lib/api'
import { useApi } from '../lib/hooks'
import type { Conversation, ConversationMessage } from '../lib/types'

export function Conversations() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const list = useApi(() => api.listConversations(50, 0), [])

  async function create() {
    if (creating) return
    setCreating(true)
    setCreateError(null)
    try {
      const created = await api.createConversation({})
      setSelectedId(created.id)
      list.reload()
    } catch (cause) {
      setCreateError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Conversations"
        subtitle="Chat with PAM's memory. History persists across restarts."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader title="Threads" subtitle="All conversations, newest activity last" />
          <div className="space-y-3 px-5 py-5">
            <button
              type="button"
              onClick={create}
              disabled={creating}
              className="rounded-md border border-accent/40 bg-accent-dim px-4 py-2 text-[13px] font-medium text-accent-soft transition-colors hover:border-accent hover:bg-accent/20 disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'New conversation'}
            </button>
            {createError ? (
              <p role="alert" className="text-[13px] text-danger">
                {createError}
              </p>
            ) : null}
            <AsyncBoundary state={list}>
              {(data) =>
                data.conversations.length === 0 ? (
                  <EmptyState
                    title="No conversations yet."
                    hint="Start one to keep follow-up context."
                  />
                ) : (
                  <ul className="divide-y divide-border rounded-md border border-border">
                    {data.conversations.map((item) => (
                      <ThreadRow
                        key={item.id}
                        item={item}
                        active={item.id === selectedId}
                        onSelect={() => setSelectedId(item.id)}
                      />
                    ))}
                  </ul>
                )
              }
            </AsyncBoundary>
          </div>
        </Card>

        {selectedId !== null ? (
          <ThreadView
            key={selectedId}
            conversationId={selectedId}
            onArchived={() => list.reload()}
          />
        ) : null}
      </div>
    </>
  )
}

function ThreadRow({
  item,
  active,
  onSelect,
}: {
  item: Conversation
  active: boolean
  onSelect: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={active}
        className={`flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-elevated/50 ${
          active ? 'bg-elevated/50' : ''
        }`}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-text">
            {item.title}
          </span>
          <span className="mt-0.5 block font-mono text-[11px] text-text-faint">
            {item.message_count} messages
          </span>
        </span>
        <StatusBadge
          status={item.status === 'active' ? 'ready' : 'disabled'}
          label={item.status}
          size="sm"
        />
      </button>
    </li>
  )
}

function ThreadView({
  conversationId,
  onArchived,
}: {
  conversationId: string
  onArchived: () => void
}) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [archiving, setArchiving] = useState(false)
  const thread = useApi(() => api.getConversation(conversationId), [conversationId])
  const history = useApi(() => api.listMessages(conversationId, 50, 0), [conversationId])
  const [extra, setExtra] = useState<ConversationMessage[]>([])

  const archived = thread.data?.status === 'archived'

  async function send(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed || sending || archived) return
    setSending(true)
    setSendError(null)
    try {
      const result = await api.askInConversation(conversationId, { question: trimmed })
      setExtra((prior) => [...prior, result.user_message, result.assistant_message])
      setDraft('')
      history.reload()
      thread.reload()
    } catch (cause) {
      setSendError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setSending(false)
    }
  }

  async function archive() {
    if (archiving || archived) return
    setArchiving(true)
    try {
      await api.archiveConversation(conversationId)
      thread.reload()
      onArchived()
    } catch (cause) {
      setSendError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setArchiving(false)
    }
  }

  const messages = [...(history.data?.messages ?? []), ...extra].filter(
    (message, index, all) => all.findIndex((other) => other.id === message.id) === index,
  )

  return (
    <Card>
      <CardHeader
        title={thread.data?.title ?? 'Conversation'}
        subtitle={archived ? 'Archived — read only' : 'Active thread'}
        action={
          archived ? null : (
            <button
              type="button"
              onClick={archive}
              disabled={archiving}
              className="rounded-md border border-border-strong bg-elevated px-3 py-1.5 text-xs font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-50"
            >
              {archiving ? 'Archiving…' : 'Archive'}
            </button>
          )
        }
      />
      <div className="space-y-4 px-5 py-5">
        <AsyncBoundary state={history}>
          {() =>
            messages.length === 0 ? (
              <EmptyState title="No messages yet." hint="Ask the first question below." />
            ) : (
              <ul className="space-y-4">
                {messages.map((message) => (
                  <MessageView key={message.id} message={message} />
                ))}
              </ul>
            )
          }
        </AsyncBoundary>

        {sendError ? (
          <p role="alert" className="text-[13px] text-danger">
            {sendError}
          </p>
        ) : null}

        {archived ? (
          <p className="text-[13px] text-text-muted">
            This conversation is archived. Start a new one to continue.
          </p>
        ) : (
          <form onSubmit={send} className="flex gap-2.5">
            <input
              type="text"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask a follow-up…"
              aria-label="Ask a follow-up question"
              className="min-w-0 flex-1 rounded-md border border-border-strong bg-bg px-3.5 py-2.5 text-[14px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
            />
            <button
              type="submit"
              disabled={sending || draft.trim().length === 0}
              className="shrink-0 rounded-md bg-accent px-5 py-2.5 text-[14px] font-medium text-on-accent transition-colors hover:bg-accent-soft disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </form>
        )}
      </div>
    </Card>
  )
}

function MessageView({ message }: { message: ConversationMessage }) {
  const mine = message.role === 'user'
  const failed = message.evidence?.error != null
  if (mine) {
    return (
      <li className="flex justify-end">
        <div className="max-w-[85%] rounded-md border border-border bg-elevated/60 px-4 py-2.5">
          <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-text">
            {message.content}
          </p>
        </div>
      </li>
    )
  }
  return (
    <li className="border-l-2 border-border pl-4">
      <p className="font-display text-[13px] italic text-text-muted">
        {message.role === 'assistant'
          ? `PAM${message.model ? ` · ${message.model}` : ''}`
          : message.role}
      </p>
      <p className="mt-1 max-w-prose text-[14px] leading-relaxed whitespace-pre-wrap text-text">
        {message.content}
      </p>
      {failed ? (
        <p role="alert" className="mt-1.5 text-[13px] text-danger">
          Generation failed and was recorded, not lost.
        </p>
      ) : null}
      {message.evidence && message.evidence.citations.length > 0 ? (
        <ul className="mt-2 space-y-1 border-t border-border pt-2">
          {message.evidence.citations.map((citation) => (
            <li
              key={`${citation.number}-${citation.source}`}
              className="font-mono text-[11px] text-text-faint"
            >
              <span className="text-accent-soft">[{citation.number}]</span>{' '}
              {citation.source}
              {citation.chunk_id ? ` · ${citation.chunk_id}` : null}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  )
}
