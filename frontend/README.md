# AI Research Copilot — Frontend

React (Vite) UI for the research copilot. Talks to the FastAPI backend over REST
and consumes the run progress over SSE.

## Run it

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000
npm run dev                 # http://localhost:5173
```

Start the backend first (`uvicorn app.main:app --reload` on port 8000). The
backend already allows the Vite dev origin via CORS.

## What's here

- **Home** (`/`) — create a session (company + meeting objective) and browse
  past briefings. Creating one starts the run and routes to its detail page.
- **Session detail** (`/sessions/:id`) — the **assembly rail** (signature) shows
  the five workflow stages lighting up live from SSE, with an event log that
  reveals the quality-check loop-back. When the run finishes, the structured
  briefing renders and follow-up chat unlocks.

## Structure

```
src/
├── main.jsx              entry + React Query provider
├── App.jsx               shell + routing
├── index.css            design system (tokens + components)
├── api/client.js        backend contract in one place
├── hooks/useRunStream.js  EventSource SSE subscription
├── pages/
│   ├── HomePage.jsx
│   └── SessionPage.jsx
└── components/
    ├── NewSessionForm.jsx
    ├── SessionList.jsx
    ├── ProgressRail.jsx   the signature element
    ├── ReportView.jsx
    ├── ChatPanel.jsx
    └── StateMessage.jsx   loading / error / empty
```

## Design notes

Server state (sessions, report, chat) is handled by React Query for built-in
loading/error/refetch; live progress is a dedicated EventSource hook. The
palette is a cool paper base with one indigo brand accent; status colors
(pending/active/done/failed) encode real workflow state. Display type is Space
Grotesk; body/data is IBM Plex Sans/Mono. Responsive down to mobile, visible
focus rings, and reduced-motion respected.
