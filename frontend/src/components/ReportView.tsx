import { useEffect, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'
import type { Report } from '../types'

const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function Sources({ sources }: { sources?: string[] }) {
  const seen = new Set<string>()
  const valid = (sources || []).filter((s) => {
    if (!s || seen.has(s)) return false
    seen.add(s)
    return true
  })
  if (valid.length === 0) return null

  return (
    <div className="sources">
      {valid.map((src, k) => {
        const host = hostOf(src)
        return (
          <a
            key={k}
            className="source-chip"
            href={src}
            target="_blank"
            rel="noreferrer"
            title={src}
          >
            <img
              className="source-favicon"
              src={`https://www.google.com/s2/favicons?domain=${host}&sz=64`}
              alt=""
              loading="lazy"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
            <span className="source-host">{host}</span>
          </a>
        )
      })}
    </div>
  )
}

function Section({
  title,
  eyebrow,
  badge,
  defaultOpen = true,
  children,
}: {
  title?: string
  eyebrow?: ReactNode
  badge?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
}) {
  return (
    <details className="card report-card" open={defaultOpen}>
      <summary className="report-card-head">
        <span className="report-card-title">
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : <h3>{title}</h3>}
        </span>
        <span className="report-card-tools">
          {badge}
          <span className="chevron" aria-hidden="true">
            ⌄
          </span>
        </span>
      </summary>
      <div className="report-card-body">{children}</div>
    </details>
  )
}

const CARD_STAGGER_MS = 320

export function ReportView({
  report,
  animate = false,
}: {
  report?: Report | null
  animate?: boolean
}) {
  if (!report) return null
  const prep = report.meeting_prep || {}
  const discoveryQuestions = prep.discovery_questions || []
  const outreachStrategy = prep.outreach_strategy || []
  const unknowns = prep.unknowns || []
  const allSources = report.sources || []

  const cards: ReactElement[] = [
    <Section
      key="exec"
      eyebrow="Executive summary"
      badge={
        typeof report.confidence === 'number' ? (
          <span className="confidence">confidence {report.confidence}</span>
        ) : null
      }
    >
      <p className="exec-text">{report.executive_summary}</p>
    </Section>,
    ...(report.sections || []).map((sec, i) => (
      <Section key={sec.key || `sec-${i}`} title={sec.title}>
        <ul className="report-points">
          {(sec.key_points || []).map((p, j) => (
            <li key={j}>{p}</li>
          ))}
        </ul>
        <Sources sources={sec.sources} />
      </Section>
    )),
  ]
  if (discoveryQuestions.length > 0) {
    cards.push(
      <Section key="discovery" title="Suggested discovery questions">
        <ol className="talking-points">
          {discoveryQuestions.map((t, i) => (
            <li key={i}>
              <span className="tp-num">{String(i + 1).padStart(2, '0')}</span>
              <span>{t}</span>
            </li>
          ))}
        </ol>
      </Section>,
    )
  }
  if (outreachStrategy.length > 0) {
    cards.push(
      <Section key="outreach" title="Suggested outreach strategy">
        <ul className="report-points">
          {outreachStrategy.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </Section>,
    )
  }
  if (unknowns.length > 0) {
    cards.push(
      <Section key="unknowns" title="Unknowns" defaultOpen={false}>
        <ul className="report-points">
          {unknowns.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </Section>,
    )
  }
  if (allSources.length > 0) {
    cards.push(
      <Section key="sources" title="Sources" defaultOpen={false}>
        <Sources sources={allSources} />
      </Section>,
    )
  }

  return (
    <ProgressiveReport cards={cards} animate={animate && !prefersReducedMotion} />
  )
}

function ProgressiveReport({
  cards,
  animate,
}: {
  cards: ReactElement[]
  animate: boolean
}) {
  const total = cards.length
  const [shown, setShown] = useState(animate ? 1 : total)

  useEffect(() => {
    if (!animate || total <= 1) {
      setShown(total)
      return undefined
    }
    setShown(1)
    let n = 1
    const id = setInterval(() => {
      n += 1
      setShown(n)
      if (n >= total) clearInterval(id)
    }, CARD_STAGGER_MS)
    return () => clearInterval(id)
  }, [total, animate])

  return (
    <div className="report">
      {cards.slice(0, shown).map((card) => (
        <div className={animate ? 'report-card-rise' : undefined} key={card.key}>
          {card}
        </div>
      ))}
    </div>
  )
}
