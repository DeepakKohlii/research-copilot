# Security & Abuse

The app is deployed as a **public demo with no authentication** — that's a
deliberate choice (a reviewer should be able to click through it without
credentials). This document is the threat model: what abuse is possible, what's
mitigated, and what's a knowingly accepted risk.

---

## Abuse vectors & mitigations

### 1. API-quota drain (the main risk)
Every briefing spends LLM + search quota; with no auth, one caller could drain it.

- **Per-IP rate limiting** on the expensive endpoints — create session, start
  run, and chat (`app/ratelimit.py`, a sliding window, default 20/min/IP,
  configurable via `RATE_LIMIT_PER_MINUTE`). Reads the real client IP from
  `X-Forwarded-For` behind Render/Vercel.
- **Bounded workflow** — research loops are capped (`max_research_passes`), and
  the whole report is a *single* batched LLM call, so cost per run is bounded.
- **Chat web search is off by default** (`CHAT_LIVE_SEARCH=false`) and, when on,
  gated to only the questions the briefing doesn't already answer.

### 2. Prompt injection (direct and indirect)
Company / website / objective and the user's chat go into LLM prompts, and chat
can include live web-search snippets — i.e. attacker-controllable text reaches
the model.

- **Blast radius is small by design:** the LLM has **no tools, no function
  calling, and no data access** — it only writes text that goes back to the same
  requester. There's no path to exfiltrate data or trigger actions.
- All free-text inputs are **length-bounded** (`pydantic` `max_length`: company
  255, website 500, objective 2000, chat 4000), limiting injection payload size.
- Residual risk (a model coaxed into off-topic output) is accepted for a demo;
  production would add output moderation and stricter system-prompt isolation.

### 3. XSS in rendered output
Model/search output is rendered in the browser.

- React **escapes text by default**, so report bullets/sections can't inject HTML.
- Chat answers render through **`react-markdown` with no raw-HTML plugin**, so
  embedded HTML is not parsed; its default URL transform also strips dangerous
  link protocols.
- **Source links are restricted to `http(s)`** (`isHttpUrl` in `ReportView`), so
  a `javascript:`/`data:` URL from a search result can't become a clickable link.

### 4. SSRF via the website field
The `website` input is **never fetched** — it's only parsed for its domain and
appended to a search *query*. No server-side request is made to a user-supplied
URL, so there's no SSRF surface.

### 5. SQL injection
All database access goes through SQLAlchemy's ORM with parameterised queries; no
endpoint builds SQL from user input. (The one raw `ALTER TABLE` in the dev
migration uses hard-coded identifiers, not user data.)

### 6. Resource / payload DoS
- Input sizes are bounded (above), so payloads can't balloon memory.
- SSE subscriptions auto-unsubscribe on disconnect and are gated by the same
  rate limit; the live tail has a keep-alive timeout.

### 7. Information disclosure
- **Secrets stay server-side** — API keys live only in backend env; the frontend
  never sees them.
- `/health` returns provider/model *names* only, never keys.
- The global exception handler returns a generic `500` — **no stack traces or
  internals leak** to the client.

### 8. Cross-origin
CORS is restricted to the **configured frontend origin(s)** (`CORS_ORIGINS`),
not a wildcard, with credentials enabled.

---

## Knowingly accepted risks (demo scope)

- **No authentication / multi-tenancy.** Sessions are global. IDs are
  unguessable UUIDv4, so enumeration is impractical, and the data is
  non-sensitive (public company research) — but there is no per-user isolation.
- **In-memory rate limiter.** Correct for the single-worker deployment; a
  multi-instance rollout would move it to Redis.
- **No per-user/global spend cap** beyond the rate limit.

## For a real production rollout
Authentication + per-user sessions and quotas, a Redis-backed distributed rate
limiter, output moderation, secret rotation, request tracing, and a WAF /
edge rate limit in front of the origin.
