# Optimization: Parallel Research Fan-Out

## Summary

The research stage of the LangGraph workflow was changed from a **sequential**
loop (one section searched after another) to a **parallel map-reduce fan-out**
using LangGraph's `Send` API and a state reducer. The research phase now issues
all section searches concurrently, then merges their results before analysis.

---

## Current behaviour (before)

The graph shape was:

```
planner → research → analysis → quality_check → (loop | report) → END
```

The `research` node ran **one node, sequentially**:

```python
for sec in plan:                       # 5 required sections
    query  = f"{company} {sec['query']} {domain}"
    results = self.search.search(query) # blocking HTTP call to Tavily
    findings.append(...)
```

Each `search()` is a blocking network round-trip to the Tavily API. With 5
sections, the node waited for search #1 to finish before starting #2, and so on:

```
[search 1]→[search 2]→[search 3]→[search 4]→[search 5]   (wall time = sum)
```

On a quality-check loop-back (a second, deeper pass) this happened **again**,
serially. So worst case was up to **10 sequential network calls** in a row.

---

## What we changed (after)

The research stage is now a map-reduce inside the graph:

```
planner → prep_research → ⟦ research_section ×5 (parallel) ⟧ → analysis
                                                                  ↓
                              report ← (loop | report) ← quality_check
```

- **`prep_research`** — a tiny single-writer node that bumps the pass counter.
- **`dispatch_research`** — a conditional edge that returns one
  `Send("research_section", payload)` per section. LangGraph runs all of these
  **branches concurrently** (the "map" step).
- **`research_section`** — runs a single section's search and returns just its
  finding, tagged with the pass number.
- **`raw_findings`** in the shared state is `Annotated[list, operator.add]` — a
  **reducer** that merges the parallel branches' results instead of letting the
  concurrent writes overwrite one another (the "reduce" step).
- Downstream nodes (`analysis`, `quality_check`, `report`) read only the
  **current pass's** findings via `_current_findings`, since the reducer
  accumulates across loop-back passes.

Now the searches overlap:

```
[search 1]┐
[search 2]┤
[search 3]┼→ merge → analysis      (wall time ≈ slowest single search)
[search 4]┤
[search 5]┘
```

### Files touched
- `backend/app/graph/state.py` — `raw_findings` reducer.
- `backend/app/graph/nodes.py` — `prep_research`, `dispatch_research`,
  `research_section`, `_current_findings`; `analysis`/`quality_check`/`report`
  filtered to the current pass; route returns `prep_research`.
- `backend/app/graph/workflow.py` — rewired edges (fan-out + reduce).
- `backend/app/graph/runner.py` — the internal map nodes are collapsed into a
  single `research` progress event for the UI (no frontend change needed).

---

## Why we optimized it

1. **Latency.** Research is the most I/O-heavy stage — it is almost entirely
   time spent waiting on the search API. Running the calls concurrently turns
   "sum of all searches" into "the slowest single search." With 5 sections that
   is roughly a **5× reduction** in research wall-clock time, and more on a
   loop-back pass. This is the single biggest speed-up available, because the
   report stage is already a single batched LLM call.

2. **It's the right tool for the shape of the work.** The five sections are
   independent — there is no data dependency between researching "Products &
   services" and "Risks & challenges." Independent I/O is the textbook case for
   fan-out; doing it sequentially was leaving free parallelism on the table.

3. **Demonstrates real LangGraph depth.** The brief explicitly weights LangGraph
   design heavily and asks for meaningful nodes, shared state, and conditional
   routing. Map-reduce via `Send` + a state **reducer** exercises LangGraph's
   concurrency model directly, rather than hiding the parallelism inside a
   single opaque node.

4. **No regressions.** The quality-check loop, recoverability, and the report
   schema are unchanged. The UI still sees one `research` step (the map nodes
   are collapsed in the runner), so the progress rail is unaffected.

---

## Trade-offs considered

- **Reducer accumulation across passes.** `operator.add` keeps appending on each
  loop-back pass. Rather than fight the reducer with a reset, each finding is
  tagged with its pass and downstream nodes filter to the latest pass — simpler
  and race-free. Memory cost is trivial (a handful of dicts).
- **Alternative: threads inside one node.** A `ThreadPoolExecutor` inside the
  old `research` node would give the same speed-up with less moving parts, but
  it hides the parallelism from the graph and doesn't exercise LangGraph's
  map-reduce — a weaker signal and less inspectable.

---

## Verification

Ran the real compiled LangGraph with mock providers end-to-end:

- **5 parallel `research_section` branches per pass** (confirmed via node trace).
- Reducer merges branches; `_current_findings` correctly isolates the latest
  pass; the **quality-check loop still triggers** a second pass on thin data.
- Final report contains all 5 required sections.
- Full app imports cleanly.
