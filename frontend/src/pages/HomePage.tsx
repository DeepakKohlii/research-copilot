import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { NewSessionForm } from '../components/NewSessionForm'
import { SessionList } from '../components/SessionList'
import { Loading, ErrorState, Empty } from '../components/StateMessage'

const FLOW = [
  { n: '01', label: 'Plan', desc: 'Scopes research angles' },
  { n: '02', label: 'Research', desc: 'Gathers live sources' },
  { n: '03', label: 'Analyze', desc: 'Synthesizes findings' },
  { n: '04', label: 'Brief', desc: 'Writes the dossier' },
]

export function HomePage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['sessions'],
    queryFn: api.listSessions,
    // Only poll while a briefing is actually in progress; once everything is
    // settled, stop polling entirely (avoids constant back-to-back calls).
    refetchInterval: (query) => {
      const active = query.state.data?.some(
        (s) => s.status === 'running' || s.status === 'queued',
      )
      return active ? 4000 : false
    },
  })

  const count = data?.length || 0

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-badge">
            <span className="hero-badge-dot" /> AI research copilot
          </span>
          <h1>
            Walk in <em>briefed</em>, not blank.
          </h1>
          <p>
            Name a company and the meeting. The copilot plans the research,
            gathers sources, checks its own coverage, and writes you a structured
            briefing you can interrogate.
          </p>

          <div className="flow">
            {FLOW.map((s) => (
              <div key={s.n} className="flow-step">
                <span className="flow-n">{s.n}</span>
                <div>
                  <div className="flow-label">{s.label}</div>
                  <div className="flow-desc">{s.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <NewSessionForm />
      </section>

      <section>
        <div className="section-head">
          <h2>Recent briefings</h2>
          {count > 0 && <span className="count">{count}</span>}
        </div>
        {isLoading && <Loading label="Loading history" />}
        {isError && (
          <ErrorState
            message={error?.message ?? 'Failed to load history'}
            onRetry={refetch}
          />
        )}
        {!isLoading && !isError && count === 0 && (
          <Empty>
            <strong>No briefings yet.</strong>
            <span>Start your first one above — it takes about 15 seconds.</span>
          </Empty>
        )}
        {!isLoading && !isError && count > 0 && (
          <SessionList sessions={data ?? []} />
        )}
      </section>
    </div>
  )
}
