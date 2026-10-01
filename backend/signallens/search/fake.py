"""Static search provider for tests: canned results, full call recording, no network.

Two ways to set it up::

    # 1. Results per exact query, with an optional fallback for any other query
    search = StaticSearch(
        {"razorpay pricing change": [SearchResult(url="https://example.com/a", title="A", snippet="...")]},
        default=[],
    )

    # 2. A handler (sync or async) that receives the query and the call options
    def handler(query, options):   # options: max_results, recency_days, include_domains, topic
        return [...]
    search = StaticSearch(handler)

A mapping value may also be an exception instance, which is raised (e.g.
``SearchError("down", retryable=True)``). A ``"default"`` key in the mapping works as the
fallback too. Like a real provider, results are deduplicated and capped at
``max_results``; with ``enforce_filters=True`` (the default) ``include_domains`` is applied
as well, so a test cannot accidentally rely on results a real provider would never return.
Every call is appended to ``search.calls`` as a dict (``query`` plus the options).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from signallens.search.base import SearchProvider, SearchResult, SearchTopic, finalize_results
from signallens.util.urls import domain_matches

__all__ = ["StaticSearch"]

SearchHandler = Callable[[str, dict[str, Any]], Sequence[SearchResult] | Awaitable[Sequence[SearchResult]]]


class StaticSearch(SearchProvider):
    """A :class:`SearchProvider` that answers from a mapping or a handler function."""

    name = "static"

    def __init__(
        self,
        results: Mapping[str, Sequence[SearchResult] | BaseException] | SearchHandler | None = None,
        *,
        default: Sequence[SearchResult] | None = None,
        enforce_filters: bool = True,
    ) -> None:
        self._handler: SearchHandler | None = None
        self._results: Mapping[str, Sequence[SearchResult] | BaseException] = {}
        if callable(results):
            self._handler = results
        elif results is not None:
            self._results = results
        self._default = default
        self._enforce_filters = enforce_filters
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def search(
        self,
        query: str,
        *,
        max_results: int = 8,
        recency_days: int | None = None,
        include_domains: list[str] | None = None,
        topic: SearchTopic = "general",
    ) -> list[SearchResult]:
        options: dict[str, Any] = {
            "max_results": max_results,
            "recency_days": recency_days,
            "include_domains": include_domains,
            "topic": topic,
        }
        self.calls.append({"query": query, **options})

        if self._handler is not None:
            found: Any = self._handler(query, dict(options))
            if inspect.isawaitable(found):
                found = await found
        elif query in self._results:
            found = self._results[query]
        elif self._default is not None:
            found = self._default
        else:
            found = self._results.get("default", [])

        if isinstance(found, BaseException):
            raise found
        results = list(found or [])
        if self._enforce_filters and include_domains:
            results = [r for r in results if domain_matches(r.url, include_domains)]
        return finalize_results(results, max(0, max_results))

    async def aclose(self) -> None:
        self.closed = True
