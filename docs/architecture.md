# Architecture

AI Research Copilot — a tool that researches a company and produces a structured,
sales-ready briefing, then lets the user interrogate it. This document describes
how the system is put together and why the pieces fit the way they do.

---

## 1. High-level shape

```
┌──────────────┐     REST + SSE      ┌──────────────────────────┐
│  React (TS)  │ ──────────────────► │   FastAPI app            │
│  Vite SPA    │ ◄────────────────── │                          │
└──────────────┘                     │  ┌────────────────────┐  │
                                     │  │ API layer (routers)│  │
                                     │  └─────────┬──────────┘  │
                                     │            │             │
                                     │  ┌─────────▼──────────┐  │
                                     │  │ Repository (ORM)   │──┼──► SQLite (dev) / Postgres (prod)
                                     │  └─────────┬──────────┘  │
                                     │            │             │
                                     │  ┌─────────▼──────────┐  │
                                     │  │ LangGraph workflow │  │
                                     │  └─────────┬──────────┘  │
                                     │            │             │
                                     │   ┌────────▼────────┐    │
                                     │   │ LLM   │ Search  │────┼──► OpenRouter / Anthropic / Ollama
                                     │   │ provider │ provider│  │     Tavily
                                     │   └─────────────────┘    │
                                     └──────────────────────────┘
```

The frontend is a single-page app. The backend is a single FastAPI process that
owns the workflow engine, persistence, and the provider integrations behind
small abstractions.

---

## 2. Backend layering

The backend is deliberately layered so each concern is swappable in isolation:

```
app/
├── main.py            FastAPI app: CORS, lifespan (DB init), routers, /health,
│                      global exception handler
├── config.py          pydantic-settings — all tunables + provider auto-resolution
├── logging_conf.py    centralised logger
├── events.py          in-memory pub/sub EventBus for live SSE fan-out
├── api/               HTTP surface (thin; no business logic)
│   ├── sessions.py    create / list / get session
│   ├── runs.py        start run + SSE progress stream
│   └── chat.py        follow-up chat (sync + streaming)
├── db/                persistence
│   ├── models.py      Session, Event, ChatMessage (SQLAlchemy)
│   ├── repository.py  the ONLY code that touches the ORM
│   └── database.py    engine, session factory, init + tiny migration
├── graph/             the LangGraph workflow
│   ├── state.py       ResearchState (shared TypedDict + reducer)
│   ├── nodes.py       the node implementations
│   ├── workflow.py    graph wiring (edges, conditional routing, fan-out)
│   └── runner.py      drives the graph, emits + persists progress events
└── services/          external-world adapters behind Protocols
    ├── llm.py         Mock | Anthropic | OpenAI-compatible (OpenRouter/Groq/Ollama)
    └── search.py      Mock | Tavily
```

**Why this shape.** The API layer never imports SQLAlchemy or an SDK — it calls
the `Repository` and the workflow. The workflow never imports `httpx` or the
Anthropic SDK — it depends on the `LLMProvider` / `SearchProvider` *Protocols*.
Swapping the database (SQLite↔Postgres — already done for prod), or Tavily for
SerpAPI, is a localised change.

---

## 3. The LangGraph workflow

The core of the product. The graph is a real multi-node state machine with
conditional routing and a parallel map-reduce stage — not a single LLM call
behind an endpoint.

```
            ┌─────────┐
            │ planner │   pick the required research sections
            └────┬────┘
                 ▼
          ┌──────────────┐
          │ prep_research│   bump pass counter
          └──────┬───────┘
                 │  dispatch_research → Send(...) × N   (fan-out / map)
        ┌────────┼────────┬────────┬────────┐
        ▼        ▼        ▼        ▼        ▼
   ┌─────────┐ ...   one research_section per section (run in parallel)
   │ research│       each does one Tavily search
   │ _section│
   └────┬────┘
        └────────┴────────┴────────┴───────► merge via raw_findings reducer (reduce)
                 ▼
           ┌──────────┐
           │ analysis │   collect/organise the current pass's findings
           └────┬─────┘
                ▼
         ┌───────────────┐   coverage score
         │ quality_check │──────────────┐
         └──────┬────────┘              │ score < threshold
                │ score ok              │ and passes < max
                ▼                       ▼
           ┌────────┐            (loop back to prep_research,
           │ report │             deeper search)
           └───┬────┘
               ▼
             END
```

**Shared state** (`ResearchState`, a `TypedDict`): inputs (company, website,
objective), `plan`, `raw_findings`, `research_passes`, `analysis`,
`quality_score`, `report`, plus bookkeeping. `raw_findings` carries an
`Annotated[list, operator.add]` **reducer** so the parallel branches merge their
results instead of overwriting each other.

**The six LangGraph requirements, mapped:**

| Requirement | How it's satisfied |
|---|---|
| Multiple meaningful nodes | planner, prep_research, research_section, analysis, quality_check, report |
| Shared graph state | `ResearchState` TypedDict, read/written by every node |
| Conditional routing | `route_after_quality` loops back to research or proceeds to report |
| Intermediate outputs | each node's result is summarised, persisted, and streamed live |
| Failure handling | a node exception is caught by the runner → session `failed` + `run_failed` event |
| Recoverability | append-only event log + checkpointer; a reconnecting client replays history |

**Report shape** (the briefing the spec requires): the `report` node makes a
*single* batched LLM call that returns JSON for all five research sections
(Company overview, Products & services, Target customers, Business signals,
Risks & challenges) plus discovery questions, outreach strategy, and unknowns —
with sources aggregated per-section and overall. Garbled/missing fields fall
back to source snippets so a briefing is always produced.

---

## 4. Progress streaming & recoverability

Progress is the part users watch, so it's built to survive disconnects.

1. The run is started by `POST /sessions/{id}/run`, which schedules the graph as
   an in-process background task and returns `202` immediately.
2. As each node completes, the **runner** does two things: persists an `Event`
   row (durable) and publishes it to an in-memory `EventBus` (live).
3. `GET /sessions/{id}/stream` is an **SSE** endpoint that first **replays the
   persisted event log**, then **live-tails** the bus (with a 20s keep-alive
   ping), de-duplicating by event id and closing on a terminal event.

This means a client that connects late, refreshes, or drops mid-run gets the
*complete* history and then the live tail — recoverability without any
client-side bookkeeping. The frontend's progress stepper is driven entirely by
this stream.

**Why SSE (not WebSockets):** the channel is one-directional (server→client);
commands are ordinary REST calls. SSE is plain HTTP — it inherits CORS, proxies,
and auth for free, and `EventSource` reconnects automatically. WebSockets'
bidirectionality would go unused. (See `engineering-decisions.md`.)

---

## 5. Persistence

SQLAlchemy over **SQLite in development** and **Postgres in production** — the
same code, switched purely by `DATABASE_URL`. Three tables:

- **sessions** — one research run (company, website, objective, status,
  current node, the final report JSON, error).
- **events** — append-only, monotonic-id progress log. This is the source of
  truth the SSE stream replays from, and what gives recoverability.
- **chat_messages** — follow-up Q&A turns.

All ORM access goes through `Repository` — nothing else imports SQLAlchemy, which
is what makes the SQLite→Postgres switch a one-line config change. The DB layer
also: normalises a `postgres://` URL to `postgresql://` (some hosts hand out the
former), and enables `pool_pre_ping` so a Postgres connection dropped while idle
(common on managed/serverless Postgres) is transparently re-established.

`init_db()` creates tables and runs a tiny forward-only column migration for the
SQLite dev path. The deployed stack uses **Neon Postgres** (see
`deployment.md`); a heavier schema-migration story (Alembic) is the natural next
step but isn't wired yet.

---

## 6. Provider abstractions (AI + search)

Both the LLM and search are behind `Protocol`s with a mock implementation, so
the entire system runs **offline and deterministically** with no keys (great for
tests and for a reviewer without API access), and flips to real providers via
config alone.

- **LLM** (`services/llm.py`): `MockLLM`, `AnthropicLLM`, and
  `OpenAICompatibleLLM` (OpenRouter / Groq / OpenAI / local Ollama — chosen from
  the key prefix). The OpenAI-compatible path is hardened for **free tiers**:
  retry/backoff on `429`/`5xx` honouring `Retry-After`, native JSON mode with a
  graceful fallback when a model rejects it, and an empty-content retry. It also
  supports token **streaming** for chat.
- **Search** (`services/search.py`): `MockSearch` (offline) and `TavilySearch`
  (real web results). Selection is automatic — a Tavily key turns on real search.

---

## 7. Request/response flows (sequence)

**Create & run a briefing**
```
UI  ── POST /sessions {company, website, objective} ─►  create row (queued)
UI  ── POST /sessions/{id}/run ─────────────────────►  202, schedule graph task
UI  ── GET  /sessions/{id}/stream (EventSource) ────►  replay log + live tail
        graph: planner→research(×N parallel)→analysis→quality_check→report
        each node → persist Event + publish to bus → SSE → stepper updates
UI  ◄─ run_completed ──────────────────────────────   refetch session → render report
```

**Follow-up chat (streaming)**
```
UI  ── POST /sessions/{id}/chat/stream {message} ──►  save user turn
        (optionally) live web search if briefing doesn't cover the question
        LLM.stream(...) → tokens
UI  ◄─ text chunks (ReadableStream) ───────────────   render live
        on completion → assistant turn persisted (fresh DB session)
```

---

## 8. Frontend

React 18 + TypeScript, Vite, React Router, TanStack Query for server state.

- **HomePage** — create form (company/website/objective, example chips) + session
  history grid.
- **SessionPage** — header with a live **progress stepper**, the assembled
  report, and a floating **chat dock** (expandable to full screen).
- Server state (sessions, chat) is cached/invalidated by TanStack Query; run
  progress comes from the SSE hook; chat tokens stream via `fetch` +
  `ReadableStream`.
- Loading and error states are first-class components; layout is responsive.

---

## 9. Configuration

Everything tunable lives in `config.py` (`pydantic-settings`, `.env`-driven):
provider keys, model selection (auto-resolved from key prefix), LLM
retries/timeout/tokens/JSON-mode, search provider, the chat live-search toggle,
and the workflow's `quality_threshold` / `max_research_passes`. No switch-flipping
between environments — set a key and the right provider is chosen. `CORS_ORIGINS`
is a comma-separated env list so the deployed frontend origin is allowed in prod.

---

## 10. Deployment topology

The two halves deploy independently:

```
Browser ──► Vercel (static SPA)  ──REST + SSE──►  Render (FastAPI, 1 worker)  ──►  Neon (Postgres)
                                                          │
                                                          └──►  Groq / OpenRouter (LLM) · Tavily (search)
```

- **Frontend → Vercel.** Static Vite build; an SPA rewrite serves `index.html`
  for client-side routes. `VITE_API_BASE_URL` (baked in at build) points at the
  backend.
- **Backend → Render** (free web service), **a single worker** — the in-memory
  event bus and the `asyncio` background runs are per-process, so multiple
  workers would split SSE subscribers from the process publishing their events.
- **Database → Neon Postgres** for persistence across restarts (Render's free
  disk is ephemeral).

Step-by-step setup, env vars, and the relevant gotchas (single worker, cold
starts, build-time frontend env) are in `deployment.md`.
