"""Workflow nodes.

Shape: Planner -> Research -> Analysis -> Quality check -> (loop back | Report)

Each node is a pure-ish function of state that returns a partial state update.
Failure handling is per-node: an exception is captured into state['errors'] and
re-raised so the runner can mark the session failed while preserving the
intermediate outputs already persisted. The quality-check + conditional edge is
the meaningful routing: thin research loops back for a deeper pass (bounded by
max_research_passes) before the report is generated.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from ..config import Settings
from ..logging_conf import get_logger
from ..services.llm import LLMProvider
from ..services.search import SearchProvider
from .state import ResearchState

log = get_logger("graph.nodes")

DEFAULT_ANGLES = [
    "company overview",
    "recent news and developments",
    "financials and funding",
    "leadership and key people",
    "products and market position",
    "competitive landscape",
]


class CopilotNodes:
    def __init__(self, llm: LLMProvider, search: SearchProvider, settings: Settings):
        self.llm = llm
        self.search = search
        self.settings = settings

    # ---- nodes ----------------------------------------------------------
    def planner(self, state: ResearchState) -> ResearchState:
        company = state["company"]
        objective = state.get("objective", "")
        log.info("[%s] planner: scoping research for %s", state["session_id"], company)
        plan = list(DEFAULT_ANGLES)
        # Light objective-aware tailoring.
        if objective and "partnership" in objective.lower():
            plan.append("partnership and integration opportunities")
        if objective and ("sell" in objective.lower() or "sales" in objective.lower()):
            plan.append("buying signals and budget indicators")
        return {"plan": plan, "current_node": "planner"}

    def research(self, state: ResearchState) -> ResearchState:
        company = state["company"]
        plan = state.get("plan", [])
        passes = state.get("research_passes", 0) + 1
        deep = passes > 1
        log.info(
            "[%s] research: pass %d (deep=%s) over %d angles",
            state["session_id"], passes, deep, len(plan),
        )
        findings: list[dict] = []
        for angle in plan:
            query = f"{company} {angle}" + (" detailed latest" if deep else "")
            results = self.search.search(query, deep=deep)
            findings.append({"angle": angle, "query": query, "results": results})
        return {
            "raw_findings": findings,
            "research_passes": passes,
            "current_node": "research",
        }

    def analysis(self, state: ResearchState) -> ResearchState:
        log.info("[%s] analysis: synthesising findings", state["session_id"])
        analysis: dict[str, list[str]] = {}
        for block in state.get("raw_findings", []):
            angle = block["angle"]
            points = [r["snippet"] for r in block["results"]]
            analysis[angle] = points
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
        """One structured LLM call that produces the whole briefing body —
        per-angle bullets, the executive summary, and meeting prep — replacing
        the former per-section + summary calls (7 → 1). Returns normalised data
        with any missing/garbled field left empty for the caller to backfill."""
        empty = {
            "executive_summary": "",
            "sections": {},
            "talking_points": [],
            "questions_to_ask": [],
            "risks": [],
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
            notes.append(f"Angle: {b['angle']}\n{lines or '  - (no results)'}")
        research_block = "\n\n".join(notes)
        angle_list = ", ".join(f'"{b["angle"]}"' for b in findings)

        raw = self.llm.complete(
            system=(
                "You are a research analyst preparing a sales-meeting briefing. "
                "Return ONLY a single valid JSON object — no markdown fences and "
                "no prose outside the JSON. Be factual and concise."
            ),
            prompt=(
                f"Company: {company}\n"
                f"Meeting objective: {objective or 'general business meeting'}\n"
                f"{source_note}\n\n"
                f"Research notes by angle:\n{research_block}\n\n"
                "Produce a JSON object with EXACTLY this shape:\n"
                "{\n"
                '  "executive_summary": "3-4 sentence prose summary",\n'
                '  "sections": [\n'
                f"    {{\"angle\": one of [{angle_list}], "
                '"key_points": ["3-4 short factual bullets"]}\n'
                "  ],\n"
                '  "talking_points": ["2-4 ways to open or steer the meeting"],\n'
                '  "questions_to_ask": ["2-4 sharp discovery questions"],\n'
                '  "risks": ["1-3 things to verify or watch out for"]\n'
                "}\n"
                "Include exactly one sections entry for every listed angle."
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
            angle = str(sec.get("angle", "")).strip().lower()
            pts = self._strlist(sec.get("key_points"), limit=4)
            if angle and pts:
                sections_map[angle] = pts

        summary = str(data.get("executive_summary", "")).strip()
        return {
            "executive_summary": summary if self._is_valid_summary(summary) else "",
            "sections": sections_map,
            "talking_points": self._strlist(data.get("talking_points"), 4),
            "questions_to_ask": self._strlist(data.get("questions_to_ask"), 4),
            "risks": self._strlist(data.get("risks"), 3),
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
        total = sum(len(b["results"]) for b in state.get("raw_findings", []))
        score = min(1.0, total / (2 * max(1, len(plan))))
        passes = state.get("research_passes", 0)
        notes = (
            f"{total} findings across {len(plan)} angles "
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
        objective = state.get("objective", "")
        log.info("[%s] report: generating briefing", state["session_id"])

        findings = state.get("raw_findings", [])
        # Single batched LLM call for the whole briefing body (bullets + summary
        # + meeting prep), instead of one call per angle plus a summary call.
        synth = self._synthesise_report(company, objective, findings)

        sections = []
        for block in findings:
            angle = block["angle"]
            # Prefer the model's bullets; fall back to source snippets (no extra
            # LLM call) if this angle is missing or the JSON was unusable.
            key_points = synth["sections"].get(angle.lower()) or (
                self._bullets_from_snippets(block["results"])
            )
            sections.append(
                {
                    "title": angle.capitalize(),
                    "key_points": key_points,
                    "sources": [r["source"] for r in block["results"] if r.get("source")],
                }
            )

        executive_summary = synth["executive_summary"] or (
            self._fallback_executive_summary(company, objective, sections)
        )

        using_mock_search = self.settings.resolved_search_provider == "mock"
        risks = list(synth["risks"])
        if using_mock_search:
            # Always surface that sources aren't live when search is mocked.
            risks.insert(
                0,
                "Verify key facts live before the meeting — search is running in "
                "mock mode (no live web results).",
            )
        elif not risks:
            risks = ["Verify key facts live before the meeting — some sources may "
                     "be dated or incomplete."]

        meeting_prep = {
            "talking_points": synth["talking_points"] or [
                f"Open with {company}'s recent momentum and shared priorities.",
                "Tie our offering to the gaps surfaced in the research.",
            ],
            "questions_to_ask": synth["questions_to_ask"] or [
                "What are your top priorities for the next two quarters?",
                "Who else is involved in evaluating a solution like ours?",
            ],
            "risks": risks[:3],
        }
        report = {
            "company": company,
            "objective": objective,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "confidence": round(state.get("quality_score", 0.0), 2),
            "executive_summary": executive_summary,
            "sections": sections,
            "meeting_prep": meeting_prep,
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
        return "research"
