import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

const EXAMPLES = ['Stripe', 'Notion', 'Databricks', 'Figma']

export function NewSessionForm() {
  const [company, setCompany] = useState('')
  const [website, setWebsite] = useState('')
  const [objective, setObjective] = useState('')
  const navigate = useNavigate()
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () => {
      const session = await api.createSession(
        company.trim(),
        website.trim(),
        objective.trim(),
      )
      await api.startRun(session.id)
      return session
    },
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      navigate(`/sessions/${session.id}`)
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (company.trim()) mutation.mutate()
  }

  return (
    <form className="card form-card" onSubmit={submit}>
      <div className="form-card-head">
        <h3>Start a briefing</h3>
        <p>Live research in seconds.</p>
      </div>

      <div className="field">
        <label htmlFor="company">Company to research</label>
        <input
          id="company"
          placeholder="e.g. Globex Corporation"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          autoFocus
        />
        <div className="examples">
          <span className="examples-label">Try</span>
          {EXAMPLES.map((name) => (
            <button
              key={name}
              type="button"
              className="example-chip"
              onClick={() => setCompany(name)}
              disabled={mutation.isPending}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="website">Website (optional)</label>
        <input
          id="website"
          placeholder="e.g. globex.com"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="objective">What's the meeting about? (optional)</label>
        <textarea
          id="objective"
          rows={3}
          placeholder="e.g. Sell our analytics platform to their growth team"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
        />
      </div>

      {mutation.isError && (
        <p className="form-error">{mutation.error?.message}</p>
      )}

      <button
        className="btn btn-primary btn-block"
        type="submit"
        disabled={!company.trim() || mutation.isPending}
      >
        {mutation.isPending ? (
          <>
            <span className="btn-spinner" /> Starting…
          </>
        ) : (
          <>
            Build the briefing <span aria-hidden="true">→</span>
          </>
        )}
      </button>
      <p className="form-hint">
        Streams live as the copilot plans, researches, and writes.
      </p>
    </form>
  )
}
