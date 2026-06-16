# Engineering Decisions

Three decisions that shaped the system, the alternatives weighed, and the
tradeoffs accepted — followed by an honest account of technical debt, the biggest
risk, and what two more weeks would buy.

---

## Decision 1 — Research as a LangGraph state machine with a parallel map-reduce stage

**Decision.** Model the work as a real LangGraph graph:
`planner → prep_research → (research_section × N in parallel) → analysis →
quality_check → (loop back | report)`. The parallel branches are fanned out with
the `Send` API and merged through an `operator.add` **reducer** on `raw_findings`.
A conditional edge loops thin research back for a deeper pass before reporting.

**Alternatives considered.**
- *A single LLM call behind an endpoint.* Simplest, but the brief explicitly
  forbids it, and it gives no place for retrieval, self-checking, or recovery.
- *Sequential research (one section after another) in a single node.* This was
  the first version. Correct, but research is almost entirely I/O wait on the
  search API, so it serialised five-plus network calls.
- *Threads inside one research node* (`ThreadPoolExecutor`). Same speed-up as the
  fan-out, less code — but it hides the parallelism from the graph and doesn't
  exercise LangGraph's concurrency model, which is the part being evaluated.

**Tradeoffs accepted.** The `Send` fan-out adds real complexity: a state reducer,
findings tagged by pass (so the reducer's accumulation across loop-backs doesn't
double-count), and a runner that collapses the internal map nodes into one
`research` event for the UI. In exchange we get roughly a **5× reduction** in
research latency (sum-of-searches → slowest-single-search), a conditional loop
that demonstrates meaningful routing, and a design that reads as a genuine
agentic workflow rather than a wrapped prompt.

---

## Decision 2 — Server-Sent Events + a durable event log for progress and recovery

**Decision.** Stream run progress over **SSE**. Every node completion is both
persisted to an append-only `events` table and published to an in-memory bus. The
stream endpoint **replays the durable log first, then live-tails** the bus,
de-duplicating by event id.

**Alternatives considered.**
- *WebSockets.* Full-duplex, but our traffic is one-directional (server→client);
  commands are ordinary REST. We'd use half the channel while paying for the
  upgrade handshake and the proxy/infra special-casing WebSockets need.
- *Client polling* (`GET /status` every second). Trivial, but laggy, chatty, and
  it can't stream chat tokens smoothly.
- *Live-only SSE with no persistence.* Simple, but a refresh or a dropped
  connection mid-run loses all progress.

**Tradeoffs accepted.** Persisting every event costs a write per node and a
little replay logic, and SSE is one-directional by design. In return we get
**recoverability for free**: a client that connects late, refreshes, or drops
gets the complete history and then the live tail, with zero client-side
bookkeeping — and SSE rides plain HTTP, inheriting CORS/proxy/auth and
auto-reconnect. The same persisted log is what makes the workflow inspectable
after the fact.

---

## Decision 3 — Mock-first provider abstractions + a single batched, free-tier-hardened report call

**Decision.** Put the LLM and search behind `Protocol`s with mock
implementations, auto-resolve the real provider from configuration, and generate
the **entire** structured briefing in **one** JSON LLM call rather than one call
per section.

**Alternatives considered.**
- *Couple directly to one SDK* (e.g. Anthropic). Fastest to write, but locks the
  project to one vendor and makes offline testing impossible.
- *One LLM call per report section + one for the summary* (the first version —
  seven calls). Conceptually clean, but slow and, on a rate-limited free tier,
  far more likely to hit limits.

**Tradeoffs accepted.** A single batched call means parsing a larger JSON object
and tolerating weaker models that wrap or pad their output — handled with a
lenient JSON extractor and snippet-based fallbacks so a briefing is always
produced. The provider indirection adds a thin layer of interfaces. In return:
the report stage drops from **7 LLM calls to 1** (~7× less latency/cost on the
stage that does all the generation); the app runs **fully offline** with mocks
(no keys needed to demo or test); and the OpenAI-compatible path is hardened for
free tiers — retry/backoff on `429`/`5xx` honouring `Retry-After`, JSON mode with
a graceful fallback, and an empty-content retry — so the common "free model
rate-limited / returned nothing" failures degrade instead of crashing the run.

---

## Top technical debt

1. **In-process background runs.** `POST /run` schedules the graph with
   `asyncio.create_task`. Fine for a single process/demo, but runs don't survive
   a restart and don't scale horizontally. Needs a real task queue
   (Celery/RQ/Arq) or a durable LangGraph checkpointer + worker.
2. **Schema migrations + the dev checkpointer.** The database itself is handled —
   SQLite in dev, **Postgres (Neon) in production**, switched by `DATABASE_URL`
   alone (the repository pattern made this a one-line change). What's still
   missing is a real **migration tool (Alembic)** — today schema changes lean on
   `create_all` plus a tiny ad-hoc column shim — and a **persistent LangGraph
   checkpointer** (the in-memory `MemorySaver` doesn't survive a restart).
3. **Test depth.** A pytest suite covers the workflow, node helpers, the API
   endpoints (incl. rate limiting), and config resolution — all offline via the
   mock providers. What's still missing is **frontend tests** and a
   **briefing-quality eval harness** (golden companies, scored sections) to catch
   prompt/model regressions.
4. **Heuristic quality gate.** `quality_check` scores *quantity* of findings, not
   semantic coverage — a company with many irrelevant hits can "pass." It also
   re-runs *all* sections on loop-back rather than only the thin ones.
5. **No auth / multi-tenancy.** Sessions are global; there's no user model,
   rate-limiting, or per-user isolation.

## Biggest technical risk

**Dependence on free/third-party model and search quality and limits.** The
output is only as good as what Tavily returns and what a free OpenRouter model
can synthesise; both have rate limits, latency spikes, and variable JSON
reliability. We've mitigated it (retries/backoff, JSON mode + tolerant parsing,
snippet fallbacks, graceful search degradation, a mock mode), but a production
deployment would need provider failover, a paid tier with quotas, response
caching, and an eval harness to catch quality regressions.

## What two more weeks would buy

1. **Durability & scale** — move runs to a real task queue and a persistent
   checkpointer, and add Alembic migrations on top of the existing Postgres. Runs
   then survive restarts and scale beyond a single worker.
2. **A test + eval suite** — pytest for nodes/routing/APIs, plus a small
   briefing-quality eval (golden companies, scored sections) to catch regressions
   when prompts or models change.
3. **Smarter quality loop** — per-section coverage scoring that re-researches
   only weak sections, and an LLM-judged coverage check instead of a raw count.
4. **Production hardening** — auth + per-user sessions and quotas, a
   Redis-backed distributed rate limiter, structured request logging/tracing,
   CI, and response caching for repeat companies. (Per-IP rate limiting, a
   Dockerfile, and a deploy are already in place.)
