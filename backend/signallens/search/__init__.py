"""Web and news search behind one interface: Tavily, Exa and Serper.

Usage::

    from signallens.search import TavilySearch

    search = TavilySearch(api_key)
    results = await search.search("Razorpay pricing", topic="news", recency_days=7)

Tests use :class:`StaticSearch` instead of a real provider.
"""

from signallens.search.base import (
    HTTPSearchProvider,
    SearchError,
    SearchProvider,
    SearchResult,
    SearchTopic,
    parse_published_date,
)
from signallens.search.exa import ExaSearch
from signallens.search.fake import StaticSearch
from signallens.search.serper import SerperSearch
from signallens.search.tavily import TavilySearch

__all__ = [
    "ExaSearch",
    "HTTPSearchProvider",
    "SearchError",
    "SearchProvider",
    "SearchResult",
    "SearchTopic",
    "SerperSearch",
    "StaticSearch",
    "TavilySearch",
    "parse_published_date",
]
