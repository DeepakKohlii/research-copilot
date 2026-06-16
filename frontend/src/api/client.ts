import type { ChatMessage, Session, SessionSummary } from '../types'

// Strip any trailing slash so a base like "https://api.example.com/" doesn't
// produce double-slash request URLs ("…com//api/sessions").
const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
)

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error(
      "Couldn't reach the research service. Check the API is running on " +
        BASE +
        '.',
    )
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null as T
  return res.json() as Promise<T>
}

export const api = {
  base: BASE,
  createSession: (company: string, website: string, objective: string) =>
    request<Session>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ company, website, objective }),
    }),
  listSessions: () => request<SessionSummary[]>('/api/sessions'),
  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),
  startRun: (id: string) =>
    request<unknown>(`/api/sessions/${id}/run`, { method: 'POST' }),
  getChat: (id: string) => request<ChatMessage[]>(`/api/sessions/${id}/chat`),
  postChat: (id: string, message: string) =>
    request<ChatMessage>(`/api/sessions/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  // Streams the assistant's answer; calls onChunk(text) as tokens arrive.
  async streamChat(
    id: string,
    message: string,
    onChunk: (text: string) => void,
  ): Promise<void> {
    let res: Response
    try {
      res = await fetch(`${BASE}/api/sessions/${id}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
    } catch {
      throw new Error("Couldn't reach the research service.")
    }
    if (!res.ok || !res.body) {
      let detail = res.statusText
      try {
        detail = (await res.json()).detail || detail
      } catch {
        /* non-JSON error body */
      }
      throw new Error(detail)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value, { stream: true })
      if (text) onChunk(text)
    }
  },
  streamUrl: (id: string) => `${BASE}/api/sessions/${id}/stream`,
}
