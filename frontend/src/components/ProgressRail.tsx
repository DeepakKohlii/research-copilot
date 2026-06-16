import type { RunEvent } from '../types'
import type { Stage } from '../hooks/usePacedReveal'

export function ProgressStepper({ stages }: { stages: Stage[] }) {
  return (
    <div className="stepper">
      {stages.map((s) => (
        <div key={s.key} className={`step ${s.status}`}>
          <span className="step-dot">{s.status === 'done' ? '✓' : s.n}</span>
          <span className="step-label">{s.label}</span>
        </div>
      ))}
    </div>
  )
}

function describe(ev: RunEvent): string {
  const d = (ev.data ?? {}) as Record<string, any>
  switch (ev.type) {
    case 'run_started':
      return `Run started for ${d.company || 'the company'}`
    case 'run_completed':
      return `Briefing ready`
    case 'run_failed':
      return `Run failed: ${d.error || 'unknown error'}`
    case 'node_completed':
      switch (ev.node) {
        case 'planner':
          return `Planned ${(d.plan || []).length} research angles`
        case 'research':
          return `Research pass ${d.pass}: ${d.total_findings} findings across ${d.angles} angles`
        case 'analysis':
          return `Analyzed ${d.angles_analysed} angles`
        case 'quality_check':
          return `Quality check — coverage score ${d.quality_score}`
        case 'report':
          return `Briefing drafted: ${d.sections} sections (confidence ${d.confidence})`
        default:
          return ev.node ?? ''
      }
    default:
      return ev.type
  }
}

export function EventLog({ events }: { events: RunEvent[] }) {
  if (!events.length) return null
  return (
    <div className="log">
      {events.map((ev) => (
        <div
          key={ev.id}
          className={`log-line ${ev.type === 'run_failed' ? 'fail' : ''}`}
        >
          <span className="ts">{ev.node ? ev.node.slice(0, 4) : '·'}</span>
          <span>{describe(ev)}</span>
        </div>
      ))}
    </div>
  )
}
