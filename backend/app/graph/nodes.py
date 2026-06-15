from __future__ import annotations

import json
import re
from datetime import datetime, timezone

try:  # location moved across langgraph versions
    from langgraph.types import Send
except ImportError:  # pragma: no cover
    from langgraph.constants import Send

from ..config import Settings
from ..logging_conf import get_logger
from ..services.llm import LLMProvider
from ..services.search import SearchProvider
from .state import ResearchState

log = get_logger("graph.nodes")

# The briefing's required research sections (per the product spec). Each drives
# a search angle and becomes a titled section in the final report, so the report
# always contains these named sections regardless of the company.
RESEARCH_SECTIONS = [
    {
        "key": "company_overview",
        "title": "Company overview",
        "query": "company overview what they do mission history headquarters",
    },
    {
        "key": "products_services",
        "title": "Products & services",
        "query": "products services product lines offerings pricing",
    },
    {
        "key": "target_customers",
        "title": "Target customers",
        "query": "target customers ideal customer profile market segments who they sell to",
    },
    {
        "key": "business_signals",
        "title": "Business signals",
        "query": "funding revenue growth hiring partnerships acquisitions recent news",
    },
    {
        "key": "risks_challenges",
        "title": "Risks & challenges",
        "query": "risks challenges competitors threats controversies headwinds",
    },
]


class CopilotNodes:
    def __init__(self, llm: LLMProvider, search: SearchProvider, settings: Settings):
        self.llm = llm
        self.search = search
        self.settings = settings

    # ---- nodes ----------------------------------------------------------
    def planner(self, state: ResearchState) -> ResearchState:
        company = state["company"]
        log.info("[%s] planner: scoping research for %s", state["session_id"], company)
        # The plan is the fixed set of required sections — copied so each run
        # owns its list and the graph state stays self-contained.
        plan = [dict(sec) for sec in RESEARCH_SECTIONS]
        return {"plan": plan, "current_node": "planner"}

    def prep_research(self, state: ResearchState) -> ResearchState:
        """Bumps the pass counter before fanning out. Kept tiny and a single
        writer so it never races with the parallel research branches."""
        passes = state.get("research_passes", 0) + 1
        log.info(
            "[%s] research: pass %d dispatching %d sections in parallel",
            state["session_id"], passes, len(state.get("plan", [])),
        )
        return {"research_passes": passes, "current_node": "research"}

    def dispatch_research(self, state: ResearchState) -> list[Send]:
        """Conditional edge: fan out one parallel `research_section` branch per
        required section (LangGraph map step). Each branch gets a self-contained
        payload so the searches run concurrently instead of one after another."""
        company = state["company"]
        passes = state.get("research_passes", 0)
        deep = passes > 1
        site = self._domain(state.get("website", ""))
        sends: list[Send] = []
        for sec in state.get("plan", []):
            query = f"{company} {sec['query']}"
            if site:
                query += f" {site}"
            if deep:
                query += " detailed latest"
            sends.append(
                Send(
                    "research_section",
                    {
                        "session_id": state["session_id"],
                        "section": sec,
                        "query": query,
                        "deep": deep,
                        "pass": passes,
                    },
                )
            )
        return sends

    def research_section(self, payload: dict) -> ResearchState:
        """One parallel branch: search a single section. Returns just its finding
        (tagged with the pass) which the `raw_findings` reducer merges with the
        other branches' results."""
        sec = payload["section"]
        results = self.search.search(payload["query"], deep=payload["deep"])
        finding = {
            "key": sec["key"],
            "title": sec["title"],
            "query": payload["query"],
            "results": results,
            "pass": payload["pass"],
        }
        return {"raw_findings": [finding]}

    @staticmethod
    def _current_findings(state: ResearchState) -> list[dict]:
        """Findings from the latest research pass only (raw_findings accumulates
        across loop-back passes via its reducer)."""
        passes = state.get("research_passes", 0)
        return [f for f in state.get("raw_findings", []) if f.get("pass") == passes]

    @staticmethod
    def _domain(website: str) -> str:
        """Bare domain from a website input ('https://www.stripe.com/x' -> 'stripe.com')."""
        if not website:
            return ""
        site = website.strip().lower()
        site = site.split("//", 1)[-1]  # drop scheme
        site = site.split("/", 1)[0]  # drop path
        return site[4:] if site.startswith("www.") else site

    def analysis(self, state: ResearchState) -> ResearchState:
        log.info("[%s] analysis: synthesising findings", state["session_id"])
        analysis: dict[str, list[str]] = {}
        for block in self._current_findings(state):
            points = [r["snippet"] for r in block["results"]]
            analysis[block["title"]] = points
        return {"analysis": analysis, "current_node": "analysis"}

    # ---- report synthesis (single batched LLM call) --------------------
    @staticmethod
    def _strlist(value, limit: int) -> list[str]:
        """Coerce an LLM-provided field into a clean, bounded list of strings."""
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            s = str(item).strip()
            if s:
                out.append(s)
        return out[:limit]

    @staticmethod
    def _parse_json_object(text: str) -> dict | None:
        """Tolerant JSON extraction: strips markdown fences and grabs the
        outermost object, so a model that wraps or pads its JSON still parses."""
        if not text:
            return None
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n?", "", t).rstrip("`").strip()
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            obj = json.loads(t[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def _bullets_from_snippets(results: list[dict]) -> list[str]:
        """Cheap, no-LLM fallback: use the cleanest source snippets as bullets."""
        bullets: list[str] = []
        for r in results:
            snip = (r.get("snippet") or "").strip()
            if snip:
                bullets.append(snip if len(snip) <= 240 else snip[:237].rstrip() + "…")
            if len(bullets) >= 3:
                break
        return bullets

    def _synthesise_report(
        self, company: str, objective: str, findings: list[dict]
    ) -> dict:
        empty = {
            "executive_summary": "",
            "sections": {},
            "discovery_questions": [],
            "outreach_strategy": [],
            "unknowns": [],
        }
        if not findings:
            return empty

        using_mock = self.settings.resolved_search_provider == "mock"
        source_note = (
            "The research notes are placeholder/demo data — base the content on "
            "well-known public facts about the company and do not mention "
            "placeholders or synthetic data."
            if using_mock
            else "Base everything on the research notes below; add only cautious, "
            "clearly-general context where the notes are thin."
        )
        notes = []
        for b in findings:
            lines = "\n".join(
                f"  - {r.get('title', 'source')}: {r.get('snippet', '')}"
                for r in b["results"]
            )
            notes.append(f"[{b['key']}] {b['title']}\n{lines or '  - (no results)'}")
        research_block = "\n\n".join(notes)
        key_list = ", ".join(f'"{b["key"]}"' for b in findings)

        raw = self.llm.complete(
            system=(
                "You are a B2B sales research analyst preparing a meeting briefing. "
                "Return ONLY a single valid JSON object — no markdown fences and "
                "no prose outside the JSON. Be factual, specific and concise."
            ),
            prompt=(
                f"Company: {company}\n"
                f"Meeting objective: {objective or 'general business meeting'}\n"
                f"{source_note}\n\n"
                f"Research notes by section:\n{research_block}\n\n"
                "Produce a JSON object with EXACTLY this shape:\n"
                "{\n"
                '  "executive_summary": "3-4 sentence prose summary",\n'
                '  "sections": [\n'
                f"    {{\"key\": one of [{key_list}], "
                '"key_points": ["3-4 short factual bullets"]}\n'
                "  ],\n"
                '  "discovery_questions": ["3-5 sharp questions to ask in the meeting"],\n'
                '  "outreach_strategy": ["3-4 bullets: how to position and approach them"],\n'
                '  "unknowns": ["2-4 important things the research could NOT determine"]\n'
                "}\n"
                "Include exactly one sections entry for every listed key. Tailor "
                "discovery_questions and outreach_strategy to the meeting objective."
            ),
            json_mode=True,
        )
        data = self._parse_json_object(raw)
        if not data:
            log.warning(
                "[report] JSON unparseable (%r); backfilling from snippets",
                (raw or "")[:80],
            )
            return empty

        sections_map: dict[str, list[str]] = {}
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            key = str(sec.get("key", "")).strip().lower()
            pts = self._strlist(sec.get("key_points"), limit=4)
            if key and pts:
                sections_map[key] = pts

        summary = str(data.get("executive_summary", "")).strip()
        return {
            "executive_summary": summary if self._is_valid_summary(summary) else "",
            "sections": sections_map,
            "discovery_questions": self._strlist(data.get("discovery_questions"), 5),
            "outreach_strategy": self._strlist(data.get("outreach_strategy"), 4),
            "unknowns": self._strlist(data.get("unknowns"), 4),
        }

    def _is_valid_summary(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        stripped = text.strip()
        if len(stripped) < 60:
            return False
        lower = stripped.lower()
        junk_markers = (
            "user safety:",
            "content policy",
            "as an ai",
            "i cannot provide",
            "i can't provide",
        )
        if any(marker in lower for marker in junk_markers) and len(stripped) < 250:
            return False
        return True

    def _fallback_executive_summary(
        self, company: str, objective: str, sections: list[dict]
    ) -> str:
        parts = [f"This briefing prepares you for a meeting with {company}."]
        if objective:
            parts.append(f"Objective: {objective}.")
        for sec in sections:
            points = sec.get("key_points", [])
            if not points:
                continue
            sentence = points[0]
            if not sentence.endswith("."):
                sentence += "."
            if len(points) > 1:
                sentence += f" {points[1]}"
                if not sentence.endswith("."):
                    sentence += "."
            parts.append(f"{sec['title']}: {sentence}")
        return " ".join(parts)

    def quality_check(self, state: ResearchState) -> ResearchState:
        plan = state.get("plan", [])
        findings = self._current_findings(state)
        total = sum(len(b["results"]) for b in findings)
        score = min(1.0, total / (2 * max(1, len(plan))))
        passes = state.get("research_passes", 0)
        notes = (
            f"{total} findings across {len(plan)} sections "
            f"(coverage score {score:.2f}, pass {passes})."
        )
        log.info("[%s] quality_check: %s", state["session_id"], notes)
        return {
            "quality_score": score,
            "quality_notes": notes,
            "current_node": "quality_check",
        }

    def report(self, state: ResearchState) -> ResearchState:
        company = state["company"]
        website = state.get("website", "")
        objective = state.get("objective", "")
        log.info("[%s] report: generating briefing", state["session_id"])

        findings = self._current_findings(state)
        # Single batched LLM call for the whole briefing body.
        synth = self._synthesise_report(company, objective, findings)

        sections = []
        all_sources: list[str] = []
        seen_sources: set[str] = set()
        for block in findings:
            # Prefer the model's bullets; fall back to source snippets (no extra
            # LLM call) if this section is missing or the JSON was unusable.
            key_points = synth["sections"].get(block["key"]) or (
                self._bullets_from_snippets(block["results"])
            )
            srcs = [r["source"] for r in block["results"] if r.get("source")]
            for s in srcs:
                if s not in seen_sources:
                    seen_sources.add(s)
                    all_sources.append(s)
            sections.append(
                {
                    "key": block["key"],
                    "title": block["title"],
                    "key_points": key_points,
                    "sources": srcs,
                }
            )

        executive_summary = synth["executive_summary"] or (
            self._fallback_executive_summary(company, objective, sections)
        )

        using_mock_search = self.settings.resolved_search_provider == "mock"
        unknowns = list(synth["unknowns"])
        # Always flag sections research couldn't cover, plus the mock-mode caveat.
        empty_titles = [s["title"] for s in sections if not s["key_points"]]
        for title in empty_titles:
            unknowns.append(f"Limited public data on {title.lower()} — verify directly.")
        if using_mock_search:
            unknowns.append(
                "Sources are demo/mock data (no live web search) — confirm facts before the meeting."
            )
        if not unknowns:
            unknowns = ["Confirm the latest figures and org changes directly before the meeting."]

        meeting_prep = {
            "discovery_questions": synth["discovery_questions"] or [
                "What are your top priorities for the next two quarters?",
                "Who else is involved in evaluating a solution like ours?",
                "What's driving the timeline for solving this now?",
            ],
            "outreach_strategy": synth["outreach_strategy"] or [
                f"Lead with {company}'s recent momentum and tie it to a shared priority.",
                "Anchor the pitch to the gaps surfaced in the research.",
                "Bring a specific, relevant proof point or customer story.",
            ],
            "unknowns": unknowns[:5],
        }
        report = {
            "company": company,
            "website": website,
            "objective": objective,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "confidence": round(state.get("quality_score", 0.0), 2),
            "executive_summary": executive_summary,
            "sections": sections,
            "meeting_prep": meeting_prep,
            "sources": all_sources,
        }
        return {"report": report, "current_node": "report"}

    # ---- conditional edge ----------------------------------------------
    def route_after_quality(self, state: ResearchState) -> str:
        score = state.get("quality_score", 0.0)
        passes = state.get("research_passes", 0)
        if score >= self.settings.quality_threshold:
            return "report"
        if passes >= self.settings.max_research_passes:
            log.info("[%s] route: max passes reached, proceeding", state["session_id"])
            return "report"
        log.info("[%s] route: quality low, looping back to research", state["session_id"])
        return "prep_research"
