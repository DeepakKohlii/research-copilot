import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import type { ChatMessage, ChatRole } from '../types'

function MessageBody({ role, content }: { role: ChatRole; content: string }) {
  if (role !== 'assistant') return <>{content}</>
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props: any) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function ChatThread({
  messages,
  streaming,
}: {
  messages: ChatMessage[]
  streaming: string | null
}) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, streaming])

  return (
    <div className="chat-thread">
      {messages.length === 0 && streaming === null && (
        <p className="chat-locked">
          Ask anything about this briefing — e.g. "What are the top risks?"
        </p>
      )}
      {messages.map((m) => (
        <div key={m.id} className={`turn ${m.role}`}>
          <span className="avatar">{m.role === 'user' ? 'You' : 'AI'}</span>
          <div className={`bubble ${m.role}`}>
            <MessageBody role={m.role} content={m.content} />
          </div>
        </div>
      ))}
      {streaming !== null && (
        <div className="turn assistant">
          <span className="avatar">AI</span>
          <div className="bubble assistant">
            {streaming === '' ? (
              <span className="thinking">Thinking…</span>
            ) : (
              <>
                <MessageBody role="assistant" content={streaming} />
                <span className="stream-caret" aria-hidden="true" />
              </>
            )}
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}

export function ChatPanel({
  sessionId,
  ready,
  suggestedQuestions = [],
  summary,
  company,
}: {
  sessionId: string
  ready: boolean
  suggestedQuestions?: string[]
  summary?: string
  company?: string
}) {
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [suggestOpen, setSuggestOpen] = useState(false)
  // null = idle; "" = sent, awaiting first token; string = answer typing in.
  const [streaming, setStreaming] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: messages = [] } = useQuery({
    queryKey: ['chat', sessionId],
    queryFn: () => api.getChat(sessionId),
    enabled: ready,
  })

  const busy = streaming !== null

  const ask = async (message: string) => {
    const msg = message.trim()
    if (!msg || busy) return
    setDraft('')

    const prev = qc.getQueryData<ChatMessage[]>(['chat', sessionId]) || []
    qc.setQueryData<ChatMessage[]>(
      ['chat', sessionId],
      [...prev, { id: `pending-${Date.now()}`, role: 'user', content: msg }],
    )
    setStreaming('')

    try {
      await api.streamChat(sessionId, msg, (chunk) => {
        setStreaming((s) => (s ?? '') + chunk)
      })
    } catch (err) {
      setStreaming(
        `⚠️ ${err instanceof Error ? err.message : 'Something went wrong.'}`,
      )
      await new Promise((r) => setTimeout(r, 1200))
    } finally {
      await qc.invalidateQueries({ queryKey: ['chat', sessionId] })
      setStreaming(null)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    ask(draft)
  }

  useEffect(() => {
    if (!open && !expanded) return undefined
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (expanded) setExpanded(false)
      else if (open) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, expanded])

  const asked = new Set(
    messages.filter((m) => m.role === 'user').map((m) => m.content),
  )
  const chips = suggestedQuestions.filter((q) => !asked.has(q)).slice(0, 4)

  const suggestions = chips.length > 0 && (
    <div className="chat-suggest">
      <button
        type="button"
        className="chat-suggest-toggle"
        onClick={() => setSuggestOpen((o) => !o)}
        aria-expanded={suggestOpen}
      >
        <span>Suggested questions</span>
        <span className="chat-suggest-count">{chips.length}</span>
        <span
          className={`chevron ${suggestOpen ? 'open' : ''}`}
          aria-hidden="true"
        >
          ⌄
        </span>
      </button>
      {suggestOpen && (
        <div className="chat-suggest-list">
          {chips.map((q, i) => (
            <button
              key={i}
              type="button"
              className="chip"
              onClick={() => ask(q)}
              disabled={busy}
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )

  const inputForm = (
    <form className="chat-input" onSubmit={submit}>
      <input
        placeholder="Ask a follow-up question…"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <button
        className="chat-send"
        type="submit"
        aria-label="Send"
        disabled={!draft.trim() || busy}
      >
        ↑
      </button>
    </form>
  )

  if (!ready) return null

  return (
    <>
      {!open && !expanded && (
        <button
          type="button"
          className="chat-launcher"
          onClick={() => setOpen(true)}
        >
          <span className="chat-launcher-icon" aria-hidden="true">
            ✦
          </span>
          Ask about this briefing
        </button>
      )}

      {open && !expanded && (
        <div className="chat-dock" role="dialog" aria-label="Follow-up chat">
          <div className="chat-dock-head">
            <div className="chat-head-text">
              <span className="chat-eyebrow">
                <span className="chat-dot" /> Follow-up chat
              </span>
              <h3>Ask about this briefing</h3>
              <p className="chat-sub">Powered by your briefing data</p>
            </div>
            <div className="chat-dock-actions">
              <button
                type="button"
                className="icon-btn"
                onClick={() => setExpanded(true)}
                aria-label="Expand to full screen"
                title="Expand"
              >
                ⤢
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                title="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <ChatThread messages={messages} streaming={streaming} />
          {suggestions}
          {inputForm}
        </div>
      )}

      {expanded && (
        <div
          className="chat-overlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.target === e.currentTarget && setExpanded(false)}
        >
          <div className="chat-full">
            <div className="chat-full-head">
              <div className="chat-head-text">
                <span className="chat-eyebrow">
                  <span className="chat-dot" /> Follow-up chat
                </span>
                <h3>{company}</h3>
              </div>
              <div className="chat-dock-actions">
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => setExpanded(false)}
                  aria-label="Collapse to dock"
                  title="Minimize"
                >
                  ⤡
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => {
                    setExpanded(false)
                    setOpen(false)
                  }}
                  aria-label="Close chat"
                  title="Close"
                >
                  ✕
                </button>
              </div>
            </div>

            {summary && (
              <div className="chat-full-summary">
                <span className="eyebrow">Executive summary</span>
                <p>{summary}</p>
              </div>
            )}

            <ChatThread messages={messages} streaming={streaming} />
            {suggestions}
            {inputForm}
          </div>
        </div>
      )}
    </>
  )
}
