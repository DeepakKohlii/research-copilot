# Deployment

How this project is deployed. Everything runs on free tiers, with the frontend
and backend hosted independently and a managed Postgres for persistence.

## Topology

```
Browser
   │
   ▼
Vercel  ── static Vite SPA, SPA-rewrite to index.html
   │   https://research-copilot-mu.vercel.app
   │
   │  REST + SSE  (VITE_API_BASE_URL baked into the build)
   ▼
Render  ── FastAPI, single uvicorn worker
   │   https://research-copilot-id8d.onrender.com   (health: /health)
   │
   ├──►  Neon        — managed Postgres (DATABASE_URL)
   ├──►  Groq        — LLM (OpenAI-compatible, llama-3.3-70b-versatile)
   └──►  Tavily      — web search
```

## What's hosted where

| Piece | Host | Notes |
|---|---|---|
| **Frontend** | **Vercel** | static Vite build; `frontend/vercel.json` rewrites every route to `index.html` so client-side routes (e.g. `/sessions/:id`) survive a refresh |
| **Backend** | **Render** (free web service) | FastAPI via `uvicorn`, **a single worker**; serves SSE; health-checked at `/health` |
| **Database** | **Neon** (free Postgres) | the production database — Render's free disk is ephemeral, so SQLite would reset on restart |
| **LLM** | **Groq** | OpenAI-compatible endpoint; model `llama-3.3-70b-versatile` |
| **Search** | **Tavily** | real web results |

## How the two halves connect

- The **frontend** calls the backend using `VITE_API_BASE_URL`
  (`https://research-copilot-id8d.onrender.com`), which Vite inlines at build
  time. Run progress comes over SSE; chat answers stream over a `fetch` body.
- The **backend** allows the frontend origin via `CORS_ORIGINS`
  (`https://research-copilot-mu.vercel.app`). An `Origin` header has no trailing
  slash, so the configured value must match exactly.

## Backend configuration (Render env vars)

| Key | Value | Purpose |
|---|---|---|
| `DATABASE_URL` | Neon Postgres URL | persistence |
| `CORS_ORIGINS` | the Vercel origin | allow the frontend |
| `SEARCH_PROVIDER` | `auto` | uses Tavily because a key is set |
| `TAVILY_API_KEY` | `tvly-…` | real web search |
| `LLM_PROVIDER` | `openai` | Groq is OpenAI-compatible |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | Groq endpoint |
| `OPENAI_API_KEY` | `gsk_…` | Groq key |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | the model |

The same code runs locally on SQLite with no keys (offline mock mode); switching
to the deployed setup is purely these environment variables.

## Repo artifacts that make it deployable

- `backend/Dockerfile` (+ `.dockerignore`) — portable backend image, binds
  `$PORT`, single worker.
- `render.yaml` — Render blueprint for the backend service.
- `frontend/vercel.json` — build + SPA rewrite for Vercel.
- `frontend/public/_redirects` — the same SPA fallback for Netlify, if used.

## Production behaviour & known limits

- **Single worker on purpose.** The in-memory event bus and the `asyncio`
  background runs are per-process, so multiple workers would split live SSE
  subscribers from the process that publishes their events. The durable event
  log still lets a reconnecting client replay full history.
- **Cold starts.** Render's free service sleeps after ~15 min idle; the first
  request then takes ~30–60s to wake.
- **Postgres handling.** The DB layer normalises `postgres://` → `postgresql://`
  and uses `pool_pre_ping` to survive Neon's idle-connection drops; tables are
  created on startup. (`psycopg2-binary` is in `requirements.txt`.)
- **Build-time frontend env.** `VITE_API_BASE_URL` is baked in at build, so
  changing the backend URL requires a frontend redeploy.
- **Background runs aren't durable.** A run scheduled with `asyncio.create_task`
  dies if the dyno restarts mid-run — acceptable for a demo; production would use
  a task queue + a persistent checkpointer (see `engineering-decisions.md`).
