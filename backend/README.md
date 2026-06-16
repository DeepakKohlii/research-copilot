# AI Research Copilot — Backend

FastAPI + LangGraph backend for an AI research copilot that briefs a user for a
sales/business meeting by researching a company and producing a structured
report. Runs fully offline in mock mode (no API key required).

## Architecture

```
React frontend  ──►  FastAPI service  ──►  LangGraph workflow  ──►  Database
   (next phase)        REST + SSE          5 nodes + QC loop      (source of truth)
        ▲                                                              │
        └──────────────────  SSE progress (read view)  ◄──────────────┘
```

- The run endpoint spawns the workflow as a background task and returns immediately.
- The workflow drives `graph.astream`; after every node the runner writes an
  `Event` row (durable) and publishes it to an in-process bus (live).
- The SSE endpoint subscribes to the bus, replays persisted events first (so a
  reconnect/refresh recovers the full timeline), then tails live updates,
  de-duplicated by event id.
- The DB is the single source of truth; SSE is a read view over it. Progress,
  intermediate outputs, failure handling and recoverability all derive from this.

### LangGraph workflow

`Planner → Research → Analysis → Quality check → (loop back to Research | Report)`

- Shared `ResearchState` TypedDict carries all data across nodes.
- The quality-check conditional edge loops back to Research for a deeper pass
  when coverage is below `QUALITY_THRESHOLD`, bounded by `MAX_RESEARCH_PASSES`.
- The checkpointer is a factory (MemorySaver in dev; swap to a persistent saver
  for cross-restart graph resume).

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # defaults to offline mock mode
uvicorn app.main:app --reload --port 8000
```

Switch to real generation by setting `LLM_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY` in `.env` (and `pip install anthropic`).

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | Create a research session |
| GET  | `/api/sessions` | List session history |
| GET  | `/api/sessions/{id}` | Session detail + report |
| POST | `/api/sessions/{id}/run` | Start the workflow (202, runs in background) |
| GET  | `/api/sessions/{id}/stream` | SSE progress (replay + live tail) |
| GET  | `/api/sessions/{id}/chat` | Chat history |
| POST | `/api/sessions/{id}/chat` | Ask a follow-up over the briefing |
| GET  | `/health` | Health check |

## Scaling path (not built; documented intentionally)

- Replace the in-process background task with a queue + worker pool (arq/Celery
  + Redis) so runs survive API restarts and scale horizontally.
- Replace SQLite with Postgres; use a persistent LangGraph checkpointer.
- Add per-node token/cost tracking — research/analysis dominate cost.
- Cache + timeout the research provider; it's the main reliability risk.
