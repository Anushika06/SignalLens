import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from signallens.search import ExaSearch, SearchError, SerperSearch, TavilySearch

TAVILY = "https://api.tavily.com/search"
EXA = "https://api.exa.ai/search"
SERPER = "https://google.serper.dev"


# --------------------------------------------------------------------------- Tavily


def _tavily_results(n=3):
    return {
        "query": "q",
        "results": [
            {
                "title": f"Result {i}",
                "url": f"https://news{i}.example.com/story-{i}",
                "content": f"Snippet   {i} text",
                "score": 0.9 - i / 10,
                "published_date": "Sun, 21 Sep 2026 10:15:00 GMT",
            }
            for i in range(n)
        ],
    }


@respx.mock
async def test_tavily_news_request_and_mapping():
    route = respx.post(TAVILY).mock(return_value=httpx.Response(200, json=_tavily_results()))
    results = await TavilySearch("tvly-key").search(
        "Razorpay funding",
        topic="news",
        recency_days=7,
        include_domains=["https://www.economictimes.com", "livemint.com"],
    )
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tvly-key"
    body = json.loads(request.content)
    assert body == {
        "query": "Razorpay funding",
        "topic": "news",
        "max_results": 8,
        "search_depth": "basic",
        "include_domains": ["economictimes.com", "livemint.com"],
        "days": 7,
    }
    assert len(results) == 3
    first = results[0]
    assert first.title == "Result 0" and first.snippet == "Snippet 0 text"
    assert first.published_at == datetime(2026, 9, 21, 10, 15, tzinfo=UTC)
    assert first.publisher == "example.com" and first.provider == "tavily"
    assert first.score == pytest.approx(0.9)


@pytest.mark.parametrize(("days", "expected"), [(1, "day"), (5, "week"), (30, "month"), (90, "year")])
@respx.mock
async def test_tavily_general_recency_uses_time_range(days, expected):
    route = respx.post(TAVILY).mock(return_value=httpx.Response(200, json={"results": []}))
    await TavilySearch("k").search("q", recency_days=days)
    body = json.loads(route.calls.last.request.content)
    assert body["time_range"] == expected and "days" not in body


@respx.mock
async def test_tavily_dedupes_by_normalized_url_and_caps_results():
    payload = {
        "results": [
            {"title": "A", "url": "https://example.com/a?utm_source=x", "content": "a"},
            {"title": "A again", "url": "https://EXAMPLE.com/a#section", "content": "a"},
            {"title": "B", "url": "https://example.com/b", "content": "b"},
            {"title": "no url", "content": "c"},
            {"title": "C", "url": "https://example.com/c", "content": "c"},
        ]
    }
    respx.post(TAVILY).mock(return_value=httpx.Response(200, json=payload))
    results = await TavilySearch("k").search("q", max_results=2)
    assert [r.title for r in results] == ["A", "B"]


@respx.mock
async def test_tavily_retries_429_then_succeeds(no_sleep):
    route = respx.post(TAVILY).mock(
        side_effect=[
            httpx.Response(429, json={"detail": {"error": "rate limit"}}),
            httpx.Response(200, json=_tavily_results(1)),
        ]
    )
    results = await TavilySearch("k").search("q")
    assert len(results) == 1 and route.call_count == 2 and no_sleep == [1.0]


@respx.mock
async def test_tavily_401_is_non_retryable(no_sleep):
    route = respx.post(TAVILY).mock(
        return_value=httpx.Response(
            401, json={"detail": {"error": "Unauthorized: missing or invalid API key."}}
        )
    )
    with pytest.raises(SearchError) as info:
        await TavilySearch("k").search("q")
    assert info.value.status == 401 and not info.value.retryable
    assert "invalid API key" in str(info.value)
    assert route.call_count == 1 and no_sleep == []


@respx.mock
async def test_search_errors_after_retries(no_sleep):
    respx.post(TAVILY).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(SearchError) as info:
        await TavilySearch("k", max_retries=1).search("q")
    assert info.value.retryable and no_sleep == [1.0]


async def test_empty_query_short_circuits():
    assert await TavilySearch("k").search("   ") == []


# --------------------------------------------------------------------------- Exa


@respx.mock
async def test_exa_request_and_mapping():
    text = "Razorpay has cut its payment gateway fee for new merchants. " * 20
    route = respx.post(EXA).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Razorpay cuts fees",
                        "url": "https://www.livemint.com/companies/razorpay-cuts-fees",
                        "publishedDate": "2026-09-20T00:00:00.000Z",
                        "text": text,
                        "score": 0.42,
                    },
                    {"title": None, "url": "https://blog.example.org/p", "publishedDate": None, "text": None},
                ]
            },
        )
    )
    results = await ExaSearch("exa-key").search(
        "Razorpay fees", topic="news", recency_days=30, include_domains=["livemint.com"]
    )
    request = route.calls.last.request
    assert request.headers["x-api-key"] == "exa-key"
    body = json.loads(request.content)
    assert body["query"] == "Razorpay fees" and body["numResults"] == 8 and body["type"] == "auto"
    assert body["includeDomains"] == ["livemint.com"] and body["category"] == "news"
    assert body["contents"] == {"text": {"maxCharacters": 3000}}
    start = datetime.strptime(body["startPublishedDate"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=UTC)
    assert abs((datetime.now(UTC) - timedelta(days=30)) - start) < timedelta(minutes=5)

    first, second = results
    assert first.published_at == datetime(2026, 9, 20, tzinfo=UTC)
    assert first.content == text
    assert len(first.snippet) <= 301 and first.snippet.endswith("…")
    assert first.publisher == "livemint.com" and first.provider == "exa"
    assert (
        second.title == "" and second.snippet == "" and second.content is None and second.published_at is None
    )


@respx.mock
async def test_exa_general_topic_has_no_category():
    route = respx.post(EXA).mock(return_value=httpx.Response(200, json={"results": []}))
    await ExaSearch("k").search("q")
    body = json.loads(route.calls.last.request.content)
    assert "category" not in body and "startPublishedDate" not in body and "includeDomains" not in body


# --------------------------------------------------------------------------- Serper


@respx.mock
async def test_serper_news_request_and_relative_dates():
    route = respx.post(f"{SERPER}/news").mock(
        return_value=httpx.Response(
            200,
            json={
                "news": [
                    {
                        "title": "T1",
                        "link": "https://economictimes.indiatimes.com/a",
                        "snippet": "S1",
                        "date": "3 hours ago",
                        "source": "ET",
                    },
                    {
                        "title": "T2",
                        "link": "https://www.livemint.com/b",
                        "snippet": "S2",
                        "date": "Sep 21, 2026",
                    },
                    {"title": "T3", "link": "https://x.example.com/c", "snippet": "S3", "date": "whenever"},
                ]
            },
        )
    )
    before = datetime.now(UTC)
    results = await SerperSearch("serper-key").search(
        "Razorpay",
        topic="news",
        recency_days=1,
        include_domains=["economictimes.indiatimes.com", "https://www.livemint.com"],
    )
    request = route.calls.last.request
    assert request.headers["x-api-key"] == "serper-key"
    body = json.loads(request.content)
    assert body == {
        "q": "Razorpay (site:economictimes.indiatimes.com OR site:livemint.com)",
        "num": 8,
        "tbs": "qdr:d",
    }
    t1, t2, t3 = results
    assert (
        before - timedelta(hours=3, minutes=1)
        <= t1.published_at
        <= datetime.now(UTC) - timedelta(hours=3) + timedelta(minutes=1)
    )
    assert t1.publisher == "indiatimes.com"
    assert t2.published_at == datetime(2026, 9, 21, tzinfo=UTC)
    assert t3.published_at is None


@pytest.mark.parametrize(("days", "tbs"), [(1, "qdr:d"), (7, "qdr:w"), (31, "qdr:m"), (365, "qdr:y")])
@respx.mock
async def test_serper_general_search_endpoint_and_tbs(days, tbs):
    route = respx.post(f"{SERPER}/search").mock(
        return_value=httpx.Response(
            200,
            json={"organic": [{"title": "O", "link": "https://razorpay.com/pricing/", "snippet": "fees"}]},
        )
    )
    results = await SerperSearch("k").search("razorpay pricing", recency_days=days)
    assert json.loads(route.calls.last.request.content)["tbs"] == tbs
    assert results[0].url == "https://razorpay.com/pricing/" and results[0].published_at is None
