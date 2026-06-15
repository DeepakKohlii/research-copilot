from __future__ import annotations

import hashlib
from typing import Protocol

from ..config import settings
from ..logging_conf import get_logger

log = get_logger("services.search")


class SearchProvider(Protocol):
    def search(self, query: str, deep: bool = False) -> list[dict]: ...


class MockSearch:
    def search(self, query: str, deep: bool = False) -> list[dict]:
        count = 3 if deep else 1
        seed = hashlib.sha1(query.encode()).hexdigest()[:8]
        results = []
        for i in range(count):
            results.append(
                {
                    "title": f"{query.title()} — finding {i + 1}",
                    "snippet": (
                        f"Synthetic insight {i + 1} for '{query}'. "
                        f"This reflects publicly reported activity (ref {seed}-{i})."
                    ),
                    "source": f"https://example.com/{seed}/{i}",
                }
            )
        return results


class TavilySearch:
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self) -> None:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is required for the tavily search provider")
        self._key = settings.tavily_api_key

    def search(self, query: str, deep: bool = False) -> list[dict]:
        import httpx

        payload = {
            "api_key": self._key,
            "query": query,
            "search_depth": "advanced" if deep else "basic",
            "max_results": 6 if deep else 4,
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            resp = httpx.post(self.ENDPOINT, json=payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  
            log.warning("Tavily search failed for %r: %s", query, exc)
            return []

        results: list[dict] = []
        for item in data.get("results", []):
            url = item.get("url", "")
            snippet = (item.get("content") or "").strip()
            if not snippet:
                continue
            results.append(
                {
                    "title": item.get("title") or query,
                    "snippet": snippet,
                    "source": url,
                }
            )
        log.info("Tavily: %d results for %r (deep=%s)", len(results), query, deep)
        return results


def get_search() -> SearchProvider:
    provider = settings.resolved_search_provider
    if provider == "tavily":
        log.info("Using Tavily search provider")
        return TavilySearch()
    log.info("Using mock search provider")
    return MockSearch()
