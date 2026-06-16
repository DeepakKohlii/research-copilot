# Product & Business Thinking

A candid product review of the AI Research Copilot — a tool that researches a
company and produces a sales-ready briefing the user can interrogate.

---

## 1. Five weaknesses in the current product design

1. **Trust gap on accuracy.** The briefing reads confidently but can't show
   *how sure* it is per claim. Sources are listed per section, but individual
   bullets aren't cited inline, so a seller can't quickly verify a specific fact.
2. **Generic output.** The five research sections are fixed and the prompt is
   the same for every company. A briefing on a 10-person startup and a public
   enterprise look structurally identical, when the useful angles differ.
3. **One-shot, not a workflow.** It produces a briefing and stops. Sellers work
   in a flow — CRM, calendar, email. Today the output lives in a tab they have to
   remember to open.
4. **No freshness signal or refresh.** A briefing is a snapshot. There's no
   "researched 6 days ago — refresh?" and no re-run that updates only what changed.
5. **Coverage is measured by quantity, not relevance.** The quality gate counts
   findings, so a company with lots of noisy hits passes while the briefing may
   still be thin on what matters for *this* meeting.

## 2. Top 3 improvements to build next (prioritised)

1. **Inline, verifiable citations** — attach a source to each bullet, with
   confidence shading. Directly closes the trust gap; it's the difference between
   "nice summary" and "something I'll walk into a meeting with."
2. **Objective-driven research** — let the meeting objective reshape the sections
   and queries (a renewal vs. a cold pitch vs. a partnership need different
   angles). Turns a generic report into a tailored one.
3. **CRM/calendar integration** — auto-generate the briefing from an upcoming
   calendar event and push it (or a summary) into the CRM record. Moves the
   product into the seller's existing flow, where retention lives.

## 3. Who buys, who uses, why they pay

- **User:** account executives, SDRs, founders, and customer-success reps — anyone
  walking into a meeting who needs to sound prepared without an hour of manual
  Googling.
- **Buyer:** the VP of Sales / RevOps, who buys it as seat-based tooling to lift
  rep productivity and consistency.
- **Why they pay:** it converts ~30–45 minutes of pre-call research into ~30
  seconds. The ROI is obvious — a rep's time is expensive, and better-prepped
  calls convert better. They'll pay because it removes a recurring, universally
  disliked chore and makes every rep look like the best-prepared one.

## 4. Success metrics

- **Activation:** % of new users who generate ≥3 briefings in week one.
- **Core value:** briefings generated per active user per week (and % opened
  again / chatted with — proof it's actually used, not just generated).
- **Quality:** thumbs-up rate on briefings; "Unknowns" shrinking over time;
  citation-click rate.
- **Retention:** week-4 and month-3 retention; % of briefings created *from a
  calendar event* (the integration habit).
- **Business:** seats expanded per account; time-to-first-briefing.

## 5. Four-week AI roadmap

- **Week 1 — Grounding & trust:** inline per-bullet citations + confidence;
  replace the count-based quality gate with an LLM-judged per-section coverage
  check.
- **Week 2 — Tailoring:** objective-aware planner (sections/queries adapt to the
  meeting goal); re-research only weak sections on loop-back.
- **Week 3 — Evals:** a golden-set briefing eval (scored sections, hallucination
  checks) wired into CI so prompt/model changes are measured, not guessed.
- **Week 4 — Freshness & chat depth:** "refresh briefing," and let the chat
  re-enter the graph for questions that need new research (not just context).

## 6. Biggest cost, scaling, and reliability risks

- **Cost:** LLM tokens and search-API calls per briefing. Mitigations already in
  place — one batched report call, gated chat search. Next: cache repeat
  companies and dedupe concurrent requests.
- **Scaling:** runs are in-process background tasks today; they won't survive
  restarts or scale horizontally. (Postgres is already in place.) The gap is a
  real task queue + workers and a persistent run checkpointer.
- **Reliability:** dependence on third-party model/search quality, limits, and
  latency. Needs provider failover, quotas, retries (partly done), and a quality
  eval to catch silent regressions.

## 7. What feature would you remove, and why

**The standalone "Suggested talking points / generic outreach" filler when it's
not grounded.** Generic, ungrounded advice ("lead with their momentum") erodes
trust faster than it helps — it makes the tool feel like a content generator.
Better to show fewer, sourced, specific recommendations than padded generic ones.

## 8. What feature would you add, and why

**A one-line "why this meeting matters" + the single best opener, grounded in a
real, recent signal** (a funding round, a launch, a hire). Sellers don't read a
full dossier 60 seconds before a call — they want the one sharp, current hook.
It's the highest-leverage thing the research can produce and the most shareable.

## 9. First 90-day roadmap

- **Days 0–30 — Trust:** inline citations + confidence, semantic quality gate,
  basic evals. Make the output something a rep relies on.
- **Days 30–60 — Fit the workflow:** calendar-triggered briefings, CRM push,
  objective-driven tailoring. Move into where sellers already work.
- **Days 60–90 — Durability & growth:** task queue + multi-worker scale-out
  (Postgres already in place), auth/multi-tenancy, team sharing, and usage
  analytics to drive seat expansion.

## 10. If you owned this product, what would you change first, and why

**Inline, verifiable citations with per-claim confidence.** Everything else —
tailoring, integrations, scale — compounds on trust. A briefing a seller can't
verify is a liability the moment one wrong fact surfaces in front of a prospect.
Make each claim checkable in one click and the product crosses the line from
"interesting demo" to "I'd actually walk into a meeting with this" — which is the
only line that matters for retention and word-of-mouth.
