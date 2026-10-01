"""Serper Google search (``POST https://google.serper.dev/search`` or ``/news``).

Serper reports dates the way Google shows them - "Sep 21, 2026" or "3 hours ago" - so they
are converted to absolute UTC datetimes relative to the time of the call.
"""

from __future__ import annotations

from datetime import UTC, datetime

from signallens.search.base import (
    HTTPSearchProvider,
    SearchResult,
    SearchTopic,
    as_list,
    clean_domains,
    finalize_results,
    parse_published_date,
)

__all__ = ["SerperSearch"]

_MAX_RESULTS = 100


def _tbs(days: int) -> str:
    if days <= 1:
        return "qdr:d"
    if days <= 7:
        return "qdr:w"
    if days <= 31:
        return "qdr:m"
    return "qdr:y"


class SerperSearch(HTTPSearchProvider):
    """Serper: Google results, organic or news."""

    name = "serper"
    base_url = "https://google.serper.dev"

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
        q = query
        domains = clean_domains(include_domains or [])
        if domains:
            q += " (" + " OR ".join(f"site:{d}" for d in domains) + ")"
        payload: dict[str, object] = {"q": q, "num": min(max_results, _MAX_RESULTS)}
        if recency_days is not None:
            payload["tbs"] = _tbs(recency_days)

        path = "/news" if topic == "news" else "/search"
        body = await self._post_json(
            f"{self.base_url}{path}", headers={"X-API-KEY": self._api_key}, payload=payload
        )
        now = datetime.now(UTC)
        items = as_list(body.get("news" if topic == "news" else "organic"))
        results = []
        for item in items:
            if not isinstance(item, dict) or not item.get("link"):
                continue
            results.append(
                SearchResult(
                    url=str(item["link"]),
                    title=str(item.get("title") or ""),
                    snippet=" ".join(str(item.get("snippet") or "").split()),
                    published_at=parse_published_date(item.get("date"), now=now),
                    provider=self.name,
                )
            )
        return finalize_results(results, max_results)
