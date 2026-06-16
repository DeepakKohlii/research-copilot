import { Link } from 'react-router-dom'
import type { SessionSummary } from '../types'

function timeAgo(iso: string): string {
  // The API sends UTC timestamps with an explicit offset, so new Date() parses
  // the correct absolute instant regardless of the viewer's timezone.
  const then = new Date(iso).getTime()
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

function prettyDomain(website?: string): string {
  if (!website) return ''
  return website
    .trim()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '')
}

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  running: 'Researching',
  completed: 'Ready',
  failed: 'Failed',
}

export function SessionList({ sessions }: { sessions: SessionSummary[] }) {
  return (
    <div className="session-grid">
      {sessions.map((s) => (
        <Link key={s.id} to={`/sessions/${s.id}`} className="session-tile">
          <div className="tile-top">
            <span className="tile-avatar">
              {(s.company || '?').trim().charAt(0).toUpperCase()}
            </span>
            <span className={`status-chip ${s.status}`}>
              <span className="status-dot" />
              {STATUS_LABEL[s.status] || s.status}
            </span>
          </div>
          <div className="tile-company">{s.company}</div>
          {s.website && (
            <span className="tile-website">{prettyDomain(s.website)}</span>
          )}
          {s.objective ? (
            <p className="tile-objective">{s.objective}</p>
          ) : (
            <p className="tile-objective muted">No objective set</p>
          )}
          <div className="tile-foot">
            <span>{timeAgo(s.created_at)}</span>
            <span className="tile-go" aria-hidden="true">
              Open →
            </span>
          </div>
        </Link>
      ))}
    </div>
  )
}
