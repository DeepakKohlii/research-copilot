export type SessionStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface ReportSection {
  key?: string
  title: string
  key_points?: string[]
  sources?: string[]
}

export interface MeetingPrep {
  discovery_questions?: string[]
  outreach_strategy?: string[]
  unknowns?: string[]
}

export interface Report {
  company?: string
  website?: string
  objective?: string
  generated_at?: string
  confidence?: number
  executive_summary?: string
  sections?: ReportSection[]
  meeting_prep?: MeetingPrep
  sources?: string[]
}

export interface Session {
  id: string
  company: string
  website?: string
  objective?: string
  status: SessionStatus
  current_node?: string | null
  report?: Report | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface SessionSummary {
  id: string
  company: string
  website?: string
  objective?: string
  status: SessionStatus
  current_node?: string | null
  created_at: string
}

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: number | string
  role: ChatRole
  content: string
  created_at?: string
}

export type RunEventType =
  | 'run_started'
  | 'node_completed'
  | 'run_completed'
  | 'run_failed'

export interface RunEvent {
  id: number
  type: RunEventType
  node?: string | null
  data?: Record<string, unknown>
}
