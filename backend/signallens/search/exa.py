"""Exa search (``POST https://api.exa.ai/search``), returning page text with each result."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from signallens.search.base import (
    HTTPSearchProvider,
    SearchResult,
    SearchTopic,
    as_list,
    clean_domains,
    finalize_results,
    make_snippet,
    parse_published_date,
)

__all__ = ["ExaSearch"]

_MAX_RESULTS = 100
_TEXT_CHARS = 3000


class ExaSearch(HTTPSearchProvider):
    """Exa: neural search; we request up to 3,000 characters of text per result."""

    name = "exa"
    endpoint = "https://api.exa.ai/search"

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
            "numResults": min(max_results, _MAX_RESULTS),
            "type": "auto",
            "contents": {"text": {"maxCharacters": _TEXT_CHARS}},
        }
        domains = clean_domains(include_domains or [])
        if domains:
            payload["includeDomains"] = domains
        if recency_days is not None:
            since = datetime.now(UTC) - timedelta(days=max(0, recency_days))
            payload["startPublishedDate"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if topic == "news":
            payload["category"] = "news"

        body = await self._post_json(self.endpoint, headers={"x-api-key": self._api_key}, payload=payload)
        results = []
        for item in as_list(body.get("results")):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            text = item.get("text") if isinstance(item.get("text"), str) else None
            score = item.get("score")
            results.append(
                SearchResult(
                    url=str(item["url"]),
                    title=str(item.get("title") or ""),
                    snippet=make_snippet(text, 300),
                    published_at=parse_published_date(item.get("publishedDate")),
                    score=float(score) if isinstance(score, int | float) else None,
                    content=text or None,
                    provider=self.name,
                )
            )
        return finalize_results(results, max_results)
