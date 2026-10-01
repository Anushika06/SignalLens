import pytest

from signallens.search import SearchError, SearchResult, StaticSearch


def _r(url, title="t"):
    return SearchResult(url=url, title=title, snippet="s")


async def test_mapping_default_and_calls():
    search = StaticSearch(
        {"razorpay pricing": [_r("https://razorpay.com/pricing/"), _r("https://news.example.com/a")]},
        default=[_r("https://fallback.example.com/")],
    )
    hits = await search.search("razorpay pricing", max_results=5, topic="news", recency_days=3)
    assert [h.url for h in hits] == ["https://razorpay.com/pricing/", "https://news.example.com/a"]
    other = await search.search("anything else")
    assert [h.url for h in other] == ["https://fallback.example.com/"]
    assert search.calls[0] == {
        "query": "razorpay pricing",
        "max_results": 5,
        "recency_days": 3,
        "include_domains": None,
        "topic": "news",
    }
    assert len(search.calls) == 2


async def test_default_key_in_mapping_and_unknown_queries():
    search = StaticSearch({"default": [_r("https://d.example.com/")]})
    assert [h.url for h in await search.search("x")] == ["https://d.example.com/"]
    assert await StaticSearch({}).search("x") == []
    assert await StaticSearch().search("x") == []


async def test_filters_like_a_real_provider():
    search = StaticSearch(
        {
            "q": [
                _r("https://razorpay.com/a"),
                _r("https://blog.razorpay.com/b"),
                _r("https://other.example.com/c"),
                _r("https://razorpay.com/a?utm_source=dup"),
            ]
        }
    )
    hits = await search.search("q", include_domains=["razorpay.com"])
    assert [h.url for h in hits] == ["https://razorpay.com/a", "https://blog.razorpay.com/b"]
    assert len(await search.search("q", max_results=1)) == 1
    unfiltered = StaticSearch({"q": [_r("https://other.example.com/c")]}, enforce_filters=False)
    assert len(await unfiltered.search("q", include_domains=["razorpay.com"])) == 1


async def test_handlers_and_errors():
    def handler(query, options):
        return [_r(f"https://example.com/{query}/{options['topic']}")]

    hits = await StaticSearch(handler).search("fees", topic="news")
    assert hits[0].url == "https://example.com/fees/news"

    async def async_handler(query, options):
        return [_r("https://example.com/async")]

    assert (await StaticSearch(async_handler).search("x"))[0].url == "https://example.com/async"

    failing = StaticSearch({"down": SearchError("provider down", retryable=True)})
    with pytest.raises(SearchError, match="provider down"):
        await failing.search("down")
