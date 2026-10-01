from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from signallens.fetch.http import FetchResult
from signallens.fetch.wayback import CDX_ENDPOINT, ArchiveCapture, WaybackClient, WaybackError

UA = "SignalLensBot/0.1 (+https://signallens.example/bot)"

CDX_ROWS = [
    ["timestamp", "original", "statuscode", "digest", "length"],
    ["20240312090000", "https://razorpay.com/pricing/", "200", "BBBB", "41000"],
    ["20240112184857", "https://razorpay.com/pricing/", "200", "TB3JAAAA", "41306"],
    ["20240215000000", "https://razorpay.com/pricing/", "-", "-", "-"],
    ["garbage-row"],
    ["notatime", "https://razorpay.com/pricing/", "200", "X", "1"],
]


class StubFetcher:
    user_agent = UA

    def __init__(self):
        self.calls = []

    async def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            content=b"<html></html>",
            text="<html></html>",
            etag=None,
            last_modified=None,
            not_modified=False,
            elapsed_ms=1,
        )


def make_client(**kwargs) -> WaybackClient:
    return WaybackClient(StubFetcher(), min_interval_s=0.0, **kwargs)


@respx.mock
async def test_list_captures_query_and_parsing():
    route = respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(200, json=CDX_ROWS))
    captures = await make_client().list_captures(
        "razorpay.com/pricing/", since=date(2024, 1, 1), until=date(2024, 12, 31), limit=12
    )
    params = dict(route.calls.last.request.url.params)
    assert params == {
        "url": "razorpay.com/pricing/",
        "output": "json",
        "fl": "timestamp,original,statuscode,digest,length",
        "filter": "statuscode:200",
        "collapse": "timestamp:6",
        "from": "20240101",
        "to": "20241231",
        "limit": "12",
    }
    assert route.calls.last.request.headers["user-agent"] == UA
    assert [c.timestamp for c in captures] == [
        "20240112184857",
        "20240215000000",
        "20240312090000",
    ]  # oldest first
    first = captures[0]
    assert first.captured_at == datetime(2024, 1, 12, 18, 48, 57, tzinfo=UTC)
    assert (first.status, first.digest, first.length) == (200, "TB3JAAAA", 41306)
    assert (captures[1].status, captures[1].digest, captures[1].length) == (None, None, None)


@pytest.mark.parametrize(("per", "collapse"), [("day", "timestamp:8"), ("all", None)])
@respx.mock
async def test_collapse_granularity(per, collapse):
    route = respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(200, json=[]))
    assert await make_client().list_captures("https://example.com/", per=per) == []
    assert route.calls.last.request.url.params.get("collapse") == collapse


@respx.mock
async def test_empty_body_means_no_captures():
    respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(200, content=b""))
    assert await make_client().list_captures("https://example.com/") == []


@respx.mock
async def test_retries_429_and_5xx_with_backoff(no_sleep):
    route = respx.get(CDX_ENDPOINT).mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("reset"),
            httpx.Response(429),
            httpx.Response(200, json=CDX_ROWS),
        ]
    )
    captures = await make_client().list_captures("https://razorpay.com/pricing/")
    assert len(captures) == 3 and route.call_count == 4
    assert no_sleep == [2.0, 5.0, 10.0]


@respx.mock
async def test_gives_up_after_retries(no_sleep):
    respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(503))
    with pytest.raises(WaybackError, match="HTTP 503"):
        await make_client().list_captures("https://razorpay.com/pricing/")
    assert no_sleep == [2.0, 5.0, 10.0]


@respx.mock
async def test_client_errors_are_not_retried(no_sleep):
    route = respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(400, text="bad query"))
    with pytest.raises(WaybackError, match="HTTP 400"):
        await make_client().list_captures("::::")
    assert route.call_count == 1 and no_sleep == []


@respx.mock
async def test_invalid_json_is_an_error():
    respx.get(CDX_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(WaybackError, match="invalid JSON"):
        await make_client().list_captures("https://razorpay.com/pricing/")


def test_capture_urls():
    capture = ArchiveCapture(
        timestamp="20240112184857",
        captured_at=datetime(2024, 1, 12, 18, 48, 57, tzinfo=UTC),
        original_url="https://razorpay.com/pricing/",
        status=200,
        digest="TB3J",
        length=41306,
    )
    assert capture.archive_url == "https://web.archive.org/web/20240112184857/https://razorpay.com/pricing/"
    assert capture.raw_url == "https://web.archive.org/web/20240112184857id_/https://razorpay.com/pricing/"


async def test_fetch_capture_uses_fetcher_without_robots():
    fetcher = StubFetcher()
    client = WaybackClient(fetcher, min_interval_s=0.0)
    capture = ArchiveCapture(
        "20240112184857", datetime(2024, 1, 12, tzinfo=UTC), "https://razorpay.com/pricing/", 200, None, None
    )
    result = await client.fetch_capture(capture)
    assert result.ok
    assert fetcher.calls == [(capture.raw_url, {"check_robots": False})]
    await client.aclose()


async def test_requests_are_paced():
    import time

    fetcher = StubFetcher()
    client = WaybackClient(fetcher, min_interval_s=0.2)
    capture = ArchiveCapture(
        "20240112184857", datetime(2024, 1, 12, tzinfo=UTC), "https://razorpay.com/pricing/", 200, None, None
    )
    started = time.perf_counter()
    await client.fetch_capture(capture)
    await client.fetch_capture(capture)
    assert time.perf_counter() - started >= 0.18


AVAILABLE = "https://archive.org/wayback/available"


@respx.mock
async def test_closest_capture_via_availability_api():
    route = respx.get(AVAILABLE).mock(return_value=httpx.Response(200, json={"archived_snapshots": {"closest": {
        "available": True, "status": "200", "timestamp": "20251002143739",
        "url": "http://web.archive.org/web/20251002143739/https://razorpay.com/pricing/"}}}))
    cap = await make_client().closest_capture("https://razorpay.com/pricing/", date(2025, 10, 1))
    assert dict(route.calls.last.request.url.params) == {"url": "https://razorpay.com/pricing/",
                                                         "timestamp": "20251001"}
    assert cap.timestamp == "20251002143739" and cap.original_url == "https://razorpay.com/pricing/"
    assert cap.raw_url == "https://web.archive.org/web/20251002143739id_/https://razorpay.com/pricing/"


@respx.mock
@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"archived_snapshots": {}}),
    httpx.Response(200, json={"archived_snapshots": {"closest": {"available": True, "status": "404",
                                                                 "timestamp": "20251002143739", "url": "x"}}}),
    httpx.Response(503, text="busy"),
    httpx.Response(200, text="not json"),
])
async def test_closest_capture_returns_none_when_unavailable(response):
    respx.get(AVAILABLE).mock(return_value=response)
    assert await make_client().closest_capture("https://razorpay.com/pricing/", date(2025, 10, 1)) is None
