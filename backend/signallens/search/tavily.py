"""Tavily search (``POST https://api.tavily.com/search``)."""

from __future__ import annotations

from signallens.search.base import (
    HTTPSearchProvider,
    SearchResult,
    SearchTopic,
    as_list,
    clean_domains,
    finalize_results,
    parse_published_date,
)

__all__ = ["TavilySearch"]

_MAX_RESULTS = 20  # API limit


def _time_range(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class TavilySearch(HTTPSearchProvider):
    """Tavily: good general/news coverage with extracted page content as the snippet."""

    name = "tavily"
    endpoint = "https://api.tavily.com/search"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 8,
        recency_days: int | None = None,
        include_domains: list[str] | None = None,
        topic: SearchTopic = "general",
    ) -> list[SearchResult]:
        query = query.strip()
        if not query or max_results <= 0:
            return []
        payload: dict[str, object] = {
            "query": query,
            "topic": topic,
            "max_results": min(max_results, _MAX_RESULTS),
            "search_depth": "basic",
        }
        domains = clean_domains(include_domains or [])
        if domains:
            payload["include_domains"] = domains
        if recency_days is not None:
            # "days" only applies to the news topic; general search takes a coarse range.
            if topic == "news":
                payload["days"] = max(1, int(recency_days))
            else:
                payload["time_range"] = _time_range(recency_days)

        body = await self._post_json(
            self.endpoint, headers={"Authorization": f"Bearer {self._api_key}"}, payload=payload
        )
        results = []
        for item in as_list(body.get("results")):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            score = item.get("score")
            results.append(
                SearchResult(
                    url=str(item["url"]),
                    title=str(item.get("title") or ""),
                    snippet=" ".join(str(item.get("content") or "").split()),
                    published_at=parse_published_date(item.get("published_date")),
                    score=float(score) if isinstance(score, int | float) else None,
                    content=item.get("raw_content") or None,
                    provider=self.name,
                )
            )
        return finalize_results(results, max_results)
