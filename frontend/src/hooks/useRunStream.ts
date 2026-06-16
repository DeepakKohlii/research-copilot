import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { RunEvent } from '../types'

const EVENT_TYPES = [
  'run_started',
  'node_completed',
  'run_completed',
  'run_failed',
] as const
const TERMINAL = new Set(['run_completed', 'run_failed'])

export type StreamStatus = 'idle' | 'open' | 'done' | 'error'

interface RunStreamOptions {
  enabled: boolean
  onDone?: (payload: RunEvent) => void
}

export function useRunStream(
  sessionId: string | undefined,
  { enabled, onDone }: RunStreamOptions,
) {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle')
  const seen = useRef<Set<number>>(new Set())
  const doneRef = useRef(onDone)
  doneRef.current = onDone

  useEffect(() => {
    if (!enabled || !sessionId) return
    setEvents([])
    seen.current = new Set()
    setStreamStatus('open')

    const es = new EventSource(api.streamUrl(sessionId))

    const handle = (e: MessageEvent) => {
      let payload: RunEvent
      try {
        payload = JSON.parse(e.data)
      } catch {
        return
      }
      if (seen.current.has(payload.id)) return
      seen.current.add(payload.id)
      setEvents((prev) => [...prev, payload])
      if (TERMINAL.has(payload.type)) {
        setStreamStatus('done')
        es.close()
        doneRef.current?.(payload)
      }
    }

    EVENT_TYPES.forEach((type) =>
      es.addEventListener(type, handle as EventListener),
    )

    es.onerror = () => {
      setStreamStatus((s) => (s === 'done' ? s : 'error'))
    }

    return () => es.close()
  }, [sessionId, enabled])

  return { events, streamStatus }
}
