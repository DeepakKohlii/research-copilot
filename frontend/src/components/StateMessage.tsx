import type { ReactNode } from 'react'

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="state">
      <div className="spinner" />
      <div className="mono">{label}</div>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="state error">
      <p style={{ margin: '0 0 12px', fontWeight: 600 }}>{message}</p>
      {onRetry && (
        <button className="btn btn-ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        ✦
      </span>
      <div className="empty-text">{children}</div>
    </div>
  )
}
