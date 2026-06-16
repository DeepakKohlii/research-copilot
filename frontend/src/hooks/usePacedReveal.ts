import { useEffect, useRef, useState } from 'react'
import type { RunEvent, SessionStatus } from '../types'

interface StageBase {
  key: string
  n: string
  label: string
  desc: string
}

export type StageStatus = 'idle' | 'active' | 'done' | 'failed'

export interface Stage extends StageBase {
  status: StageStatus
}

export const STAGES: StageBase[] = [
  { key: 'planner', n: '01', label: 'Plan', desc: 'Scope the research angles' },
  { key: 'research', n: '02', label: 'Research', desc: 'Gather sources' },
  { key: 'analysis', n: '03', label: 'Analyze', desc: 'Synthesize findings' },
  { key: 'quality_check', n: '04', label: 'Quality check', desc: 'Score coverage' },
  { key: 'report', n: '05', label: 'Brief', desc: 'Write the briefing' },
]

const ORDER = STAGES.map((s) => s.key)

const MIN_STEP_MS = 650

const revealedCache = new Map<string | undefined, number>()

function stageStatuses(
  events: RunEvent[],
  runStatus: SessionStatus | undefined,
  live: boolean,
): Stage[] {
  let lastNode: string | null = null
  let failedNode: string | null = null
  for (const ev of events) {
    if (ev.type === 'node_completed' && ev.node) lastNode = ev.node
    if (ev.type === 'run_failed') failedNode = lastNode
  }

  const activeIdx = lastNode ? ORDER.indexOf(lastNode) + 1 : 0
  const allDone = runStatus === 'completed' && !live && !failedNode

  return STAGES.map((s, i) => {
    let status: StageStatus = 'idle'
    if (failedNode === s.key) status = 'failed'
    else if (allDone || i < activeIdx) status = 'done'
    else if (i === activeIdx && live) status = 'active'
    return { ...s, status }
  })
}

export function usePacedReveal(
  sessionId: string | undefined,
  events: RunEvent[],
  runStatus: SessionStatus | undefined,
) {
  const total = events.length

  const [shown, setShown] = useState<number>(() => {
    const cached = revealedCache.get(sessionId) ?? 0
    if (runStatus === 'completed' || runStatus === 'failed') {
      return Math.max(cached, total)
    }
    return cached
  })

  const lastAt = useRef(0)

  useEffect(() => {
    const cached = revealedCache.get(sessionId) ?? 0
    if (shown > cached) revealedCache.set(sessionId, shown)
  }, [sessionId, shown])

  useEffect(() => {
    if (shown >= total) return undefined
    const wait = Math.max(0, MIN_STEP_MS - (Date.now() - lastAt.current))
    const t = setTimeout(() => {
      lastAt.current = Date.now()
      setShown((n) => n + 1)
    }, wait)
    return () => clearTimeout(t)
  }, [shown, total])

  const revealed = events.slice(0, shown)
  const revealing = shown < total
  const live = runStatus === 'running' || runStatus === 'queued' || revealing
  const stages = stageStatuses(revealed, runStatus, live)

  return { stages, revealed }
}
