# AI Research Copilot

> Walk into the meeting briefed, not blank.

A production-minded AI Research Copilot built with **LangGraph**. Give it a
company, a website, and what the meeting is about; it runs a multi-step research
workflow — planning, parallel web research, analysis, a self-check loop, and
report generation — and produces a structured, sourced briefing you can then
**chat with**.

**Stack:** React + TypeScript (Vite) · Python + FastAPI · LangGraph · SQLite (dev)
/ Postgres (prod) · Tavily search · Groq / OpenRouter / Anthropic / Ollama (any
OpenAI-compatible LLM). Deployed on Vercel (frontend) + Render (backend) + Neon
(Postgres).

---

## What it does

1. **Create a research session** — company name, website, research objective.
2. **Run a LangGraph workflow** and watch progress stream in live.
3. **Get a structured briefing** — Company overview, Products & services, Target
   customers, Business signals, Risks & challenges, Suggested discovery
   questions, Suggested outreach strategy, Unknowns, and Sources.
4. **Ask follow-up questions** — chat grounded in the briefing, with optional
   live web search for things the briefing didn't cover.
5. **Everything persists** — sessions, the full progress event log, and chat.

### Highlights
- **Real LangGraph workflow** — multiple nodes, shared state, a conditional
  quality-check loop, and a **parallel `Send` map-reduce** research stage with a
  state reducer (not a single LLM call behind an endpoint).
- **Live progress over SSE** with a **durable event log**, so a refresh or
  dropped connection replays the full history (recoverability).
- **Runs fully offline** with mock providers — no API keys needed to try it.
- **Free-tier hardened** LLM path — retries/backoff on rate limits, JSON mode
  with graceful fallback, and a single batched report call.

---

## Quick start

You need **Python 3.11+** and **Node 18+**.

### 1. Backend (`http://localhost:8000`)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env          # works out of the box in mock mode
uvicorn app.main:app --reload
```

It runs **offline with mock data** out of the box. To use real models and search,
edit `.env`:

```bash
# Real web search (free key at tavily.com)
SEARCH_PROVIDER=auto
TAVILY_API_KEY=tvly-...

# An LLM — provider is auto-detected from the key prefix
OPENAI_API_KEY=sk-or-...                              # OpenRouter
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
# or ANTHROPIC_API_KEY=sk-ant-...   or a local Ollama base URL
```

### 2. Frontend (`http://localhost:5173`)

```bash
cd frontend
npm install
npm run dev
```

The frontend talks to `http://localhost:8000` by default. To point elsewhere,
set `VITE_API_BASE_URL` in `frontend/.env`.

Open `http://localhost:5173` and start a briefing.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/sessions` | Create a session (`company`, `website`, `objective`) |
| `GET`  | `/api/sessions` | List session history |
| `GET`  | `/api/sessions/{id}` | Session detail (+ report once complete) |
| `POST` | `/api/sessions/{id}/run` | Start the LangGraph run (returns `202`) |
| `GET`  | `/api/sessions/{id}/stream` | Live progress (SSE; replays history) |
| `GET`  | `/api/sessions/{id}/chat` | Chat history |
| `POST` | `/api/sessions/{id}/chat` | Ask a follow-up |
| `POST` | `/api/sessions/{id}/chat/stream` | Ask a follow-up (token streaming) |
| `GET`  | `/health` | Health + active providers |

---

## Configuration

All settings live in `backend/app/config.py` and are overridable via `.env`:

| Setting | Default | What it does |
|---|---|---|
| `SEARCH_PROVIDER` | `auto` | `auto` uses Tavily if a key is set, else `mock` |
| `TAVILY_API_KEY` | — | enables real web search |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | enables a real LLM (provider auto-detected) |
| `LLM_MODEL` | per-provider default | override the model |
| `QUALITY_THRESHOLD` | `0.7` | coverage score needed to skip the research loop |
| `MAX_RESEARCH_PASSES` | `2` | cap on quality-check loop-backs |
| `LLM_MAX_RETRIES` | `4` | retries for rate-limited free tiers |
| `CHAT_LIVE_SEARCH` | `false` | when `true`, let chat web-search only the questions the briefing doesn't cover (off by default to save search-API cost) |
| `RATE_LIMIT_PER_MINUTE` | `20` | per-IP cap on expensive endpoints (create / run / chat) |
| `CORS_ORIGINS` | localhost | comma-separated allowed frontend origins (set in prod) |

---

## Project structure

```
backend/        FastAPI app, LangGraph workflow, persistence, providers
frontend/       React + TypeScript SPA (Vite)
docs/           architecture, engineering decisions, product thinking
```

```
backend/app/
├── api/        sessions · runs (+ SSE) · chat
├── db/         models · repository · database
├── graph/      state · nodes · workflow · runner   ← the LangGraph workflow
├── services/   llm · search   ← provider abstractions (mock + real)
├── ratelimit.py  config.py  logging_conf.py  events.py  main.py
```

---

## Tests

The mock providers let the whole suite run **offline and deterministically** —
no API keys, no network:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Covers the LangGraph workflow (parallel fan-out, the quality loop, the required
report sections), the node helpers, the API endpoints (CRUD, validation, 404s,
chat gating, rate limiting), and config/provider resolution.

---

## Documentation

- [**docs/architecture.md**](docs/architecture.md) — system design, the LangGraph
  workflow, streaming & recoverability, persistence, providers.
- [**docs/engineering-decisions.md**](docs/engineering-decisions.md) — the three
  major decisions, alternatives, tradeoffs, technical debt, and risks.
- [**docs/product-improvements.md**](docs/product-improvements.md) — product and
  business thinking, roadmap, and metrics.
- [**docs/deployment.md**](docs/deployment.md) — how the live deployment is set
  up (Vercel + Render + Neon Postgres).
- [**docs/security.md**](docs/security.md) — threat model: abuse vectors,
  mitigations, and accepted risks.
- [**docs/parallel-research-optimization.md**](docs/parallel-research-optimization.md)
  — deep-dive on the parallel research fan-out.

---

## How the workflow works

```
planner → prep_research → (research_section × N, in parallel) → analysis
                                                                   │
   report ◄── (loop back if coverage is thin) ◄── quality_check ◄─┘
```

The planner scopes the required sections; research fans out one parallel branch
per section (each a web search) and merges results through a state reducer;
analysis organises them; the quality check loops back for a deeper pass if
coverage is thin (bounded); and the report node makes a single batched LLM call
that returns the full structured briefing. Every node's progress is persisted and
streamed live.
