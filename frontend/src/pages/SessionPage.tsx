import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { ProgressStepper, EventLog } from '../components/ProgressRail'
import { ReportView } from '../components/ReportView'
import { ChatPanel } from '../components/ChatPanel'
import { Loading, ErrorState } from '../components/StateMessage'
import { useRunStream } from '../hooks/useRunStream'
import { usePacedReveal } from '../hooks/usePacedReveal'

function formatUpdated(ts?: string | null): string | null {
  if (!ts) return null
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return null
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (sameDay) return `Updated today at ${time}`
  return `Updated ${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${time}`
}

export function SessionPage() {
  const { id = '' } = useParams()
  const qc = useQueryClient()

  const {
    data: session,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['session', id],
    queryFn: () => api.getSession(id),
  })

  const streaming =
    !!session && (session.status === 'running' || session.status === 'queued')

  const onDone = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['session', id] })
    qc.invalidateQueries({ queryKey: ['sessions'] })
  }, [qc, id])

  const { events } = useRunStream(id, { enabled: streaming, onDone })

  const [sawLive, setSawLive] = useState(false)
  useEffect(() => {
    if (
      session &&
      (session.status === 'running' || session.status === 'queued')
    ) {
      setSawLive(true)
    }
  }, [session?.status])

  const { stages, revealed } = usePacedReveal(id, events, session?.status)

  if (isLoading)
    return (
      <div className="page">
        <Loading label="Loading session" />
      </div>
    )
  if (isError || !session)
    return (
      <div className="page">
        <ErrorState
          message={error?.message ?? 'Session not found'}
          onRetry={refetch}
        />
      </div>
    )

  const completed = session.status === 'completed'
  const updated = formatUpdated(session.updated_at || session.created_at)
  const questions = session.report?.meeting_prep?.discovery_questions || []
  const websiteHref = session.website
    ? /^https?:\/\//.test(session.website)
      ? session.website
      : `https://${session.website}`
    : null

  return (
    <div className="page">
      <Link to="/" className="backlink">
        ← All briefings
      </Link>

      <header className="session-head">
        <div className="session-head-main">
          <h1>{session.company}</h1>
          <div className="session-head-meta">
            <span className={`pill ${session.status}`}>{session.status}</span>
            {websiteHref && (
              <a
                className="head-website"
                href={websiteHref}
                target="_blank"
                rel="noreferrer"
              >
                {session.website}
              </a>
            )}
            {updated && <span className="updated">{updated}</span>}
          </div>
          {session.objective && <p className="objective">{session.objective}</p>}
        </div>
        <ProgressStepper stages={stages} />
      </header>

      {session.status === 'failed' && (
        <ErrorState
          message={session.error || 'The run failed. Start a new briefing.'}
        />
      )}

      <div className="session-body">
        {completed && session.report ? (
          <ReportView report={session.report} animate={sawLive} />
        ) : (
          session.status !== 'failed' && (
            <div className="card work-card">
              <Loading label="Compiling the briefing…" />
              <EventLog events={revealed} />
            </div>
          )
        )}
      </div>

      <ChatPanel
        sessionId={id}
        ready={completed && !!session.report}
        suggestedQuestions={questions}
        summary={session.report?.executive_summary}
        company={session.company}
      />
    </div>
  )
}
