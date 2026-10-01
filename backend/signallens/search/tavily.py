"""Tavily search (``POST https://api.tavily.com/search``) and page extraction (``/extract``).

Extraction matters for egress-restricted runtimes (the aiKart sandbox): when the container
may only reach ``api.tavily.com``, Tavily fetches official pages on our behalf.
"""

from __future__ import annotations

from dataclasses import dataclass

from signallens.search.base import (
    HTTPSearchProvider,
    SearchResult,
    SearchTopic,
    as_list,
    clean_domains,
    finalize_results,
    parse_published_date,
)

__all__ = ["ExtractedContent", "TavilySearch"]

_MAX_RESULTS = 20  # API limit
_MAX_EXTRACT_URLS = 20  # API limit per request


@dataclass
class ExtractedContent:
    """One URL read through Tavily Extract: ``content`` is the page text, empty on failure."""

    url: str
    content: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.content.strip()) and self.error is None


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
    extract_endpoint = "https://api.tavily.com/extract"

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

    async def extract(self, urls: list[str], *, depth: str = "basic") -> list[ExtractedContent]:
        """Read pages through Tavily Extract; one entry per requested URL, in request order.

        Failed URLs come back with ``error`` set instead of raising, so a caller reading five
        pages still gets the four that worked. Transport/HTTP failures of the call itself
        raise :class:`~signallens.search.base.SearchError` like :meth:`search`.
        """
        wanted = [u.strip() for u in urls if u and u.strip()][:_MAX_EXTRACT_URLS]
        if not wanted:
            return []
        body = await self._post_json(
            self.extract_endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            payload={"urls": wanted, "extract_depth": depth},
        )
        found: dict[str, ExtractedContent] = {}
        for item in as_list(body.get("results")):
            if isinstance(item, dict) and item.get("url"):
                url = str(item["url"])
                found[url] = ExtractedContent(url=url, content=str(item.get("raw_content") or ""))
        for item in as_list(body.get("failed_results")):
            if isinstance(item, dict) and item.get("url"):
                url = str(item["url"])
                found.setdefault(url, ExtractedContent(url=url, content="", error=str(item.get("error") or "failed")))
        out = []
        for url in wanted:
            hit = found.get(url) or found.get(url.rstrip("/")) or found.get(url + "/")
            out.append(hit or ExtractedContent(url=url, content="", error="not returned by Tavily"))
        return out
