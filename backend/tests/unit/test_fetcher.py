import time

import httpx
import pytest
import respx

from signallens.fetch.http import Fetcher, decode_body

UA = "SignalLensBot/0.1 (+https://signallens.example/bot)"
PAGE = "https://example.com/pricing/"


def make_fetcher(**overrides) -> Fetcher:
    options = {"user_agent": UA, "min_host_interval_s": 0.0, "respect_robots": False}
    options.update(overrides)
    return Fetcher(**options)


@pytest.fixture(autouse=True)
def _dns(fake_dns):
    """Every test here resolves hosts through the fake resolver (public by default)."""
    return fake_dns


@respx.mock
async def test_successful_html_fetch_sends_polite_headers():
    route = respx.get(PAGE).mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body>Fees: 2%</body></html>",
            headers={
                "content-type": "text/html; charset=utf-8",
                "etag": '"v1"',
                "last-modified": "Mon, 28 Sep 2026 10:00:00 GMT",
            },
        )
    )
    result = await make_fetcher().fetch(PAGE)
    assert result.ok and result.status == 200
    assert result.text == "<html><body>Fees: 2%</body></html>"
    assert result.etag == '"v1"' and result.last_modified == "Mon, 28 Sep 2026 10:00:00 GMT"
    assert result.final_url == PAGE and not result.not_modified and not result.from_sandbox
    assert result.media_type == "text/html"
    headers = route.calls.last.request.headers
    assert headers["user-agent"] == UA
    assert headers["accept"] == "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"
    assert headers["accept-language"] == "en"


@respx.mock
async def test_conditional_request_and_304():
    route = respx.get(PAGE).mock(return_value=httpx.Response(304))
    result = await make_fetcher().fetch(PAGE, etag='"v1"', last_modified="Mon, 28 Sep 2026 10:00:00 GMT")
    request = route.calls.last.request
    assert request.headers["if-none-match"] == '"v1"'
    assert request.headers["if-modified-since"] == "Mon, 28 Sep 2026 10:00:00 GMT"
    assert result.not_modified and result.status == 304 and not result.ok
    assert result.content == b"" and result.text is None
    assert result.etag == '"v1"'  # carried over when the 304 does not repeat it


@respx.mock
async def test_max_bytes_from_content_length():
    respx.get(PAGE).mock(
        return_value=httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/html"})
    )
    result = await make_fetcher(max_bytes=1000).fetch(PAGE)
    assert result.blocked == "too_large" and not result.ok and result.content == b""


@respx.mock
async def test_max_bytes_while_streaming():
    async def body():
        for _ in range(50):
            yield b"y" * 100

    respx.get(PAGE).mock(
        return_value=httpx.Response(200, content=body(), headers={"content-type": "text/html"})
    )
    result = await make_fetcher(max_bytes=1000).fetch(PAGE)
    assert result.blocked == "too_large"


@respx.mock
async def test_follows_redirects_manually():
    respx.get("http://example.com/pricing").mock(
        return_value=httpx.Response(301, headers={"location": "https://example.com/pricing"})
    )
    respx.get("https://example.com/pricing").mock(
        return_value=httpx.Response(302, headers={"location": "/pricing/"})
    )
    respx.get(PAGE).mock(
        return_value=httpx.Response(200, text="final", headers={"content-type": "text/plain"})
    )
    result = await make_fetcher().fetch("http://example.com/pricing")
    assert result.ok and result.text == "final"
    assert result.url == "http://example.com/pricing" and result.final_url == PAGE


@respx.mock
async def test_redirect_to_private_ip_is_blocked():
    respx.get(PAGE).mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    )
    metadata = respx.get("http://169.254.169.254/latest/meta-data/").mock(
        return_value=httpx.Response(200, text="secrets")
    )
    result = await make_fetcher().fetch(PAGE)
    assert result.blocked == "ssrf" and result.status is None
    assert result.final_url == "http://169.254.169.254/latest/meta-data/"
    assert not metadata.called


@respx.mock
async def test_redirect_to_host_resolving_privately_is_blocked(fake_dns):
    fake_dns.records["internal.example.net"] = ["10.0.0.8"]
    respx.get(PAGE).mock(
        return_value=httpx.Response(302, headers={"location": "https://internal.example.net/admin"})
    )
    result = await make_fetcher().fetch(PAGE)
    assert result.blocked == "ssrf"


async def test_private_start_url_is_blocked_without_request():
    with respx.mock(assert_all_called=False) as router:
        route = router.get("http://localhost:8000/").mock(return_value=httpx.Response(200))
        result = await make_fetcher().fetch("http://localhost:8000/")
    assert result.blocked == "ssrf" and not route.called


@respx.mock
async def test_allow_private_hosts_for_development():
    respx.get("http://localhost:8000/page").mock(
        return_value=httpx.Response(200, text="dev", headers={"content-type": "text/plain"})
    )
    result = await make_fetcher(allow_private_hosts=True).fetch("http://localhost:8000/page")
    assert result.ok and result.text == "dev"


@respx.mock
async def test_redirect_loop_is_an_error():
    respx.get("https://example.com/a").mock(return_value=httpx.Response(302, headers={"location": "/b"}))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(302, headers={"location": "/a"}))
    result = await make_fetcher(max_redirects=3).fetch("https://example.com/a")
    assert result.error and "too many redirects" in result.error and not result.ok


@respx.mock
async def test_redirect_to_other_scheme_is_blocked():
    respx.get(PAGE).mock(return_value=httpx.Response(302, headers={"location": "ftp://example.com/file"}))
    result = await make_fetcher().fetch(PAGE)
    assert result.blocked == "unsupported_scheme"


@pytest.mark.parametrize("url", ["http://[not-ipv6/x", "https://example.com:99999/"])
async def test_malformed_urls_are_errors_not_blocks(url):
    result = await make_fetcher().fetch(url)
    assert result.error and result.error.startswith("invalid URL") and result.blocked is None


async def test_unsupported_scheme():
    result = await make_fetcher().fetch("ftp://example.com/x")
    assert result.blocked == "unsupported_scheme" and not result.ok


@respx.mock
async def test_network_errors_never_raise():
    respx.get("https://down.example.com/").mock(side_effect=httpx.ConnectError("connection refused"))
    respx.get("https://slow.example.com/").mock(side_effect=httpx.ReadTimeout("read timed out"))
    fetcher = make_fetcher()
    down = await fetcher.fetch("https://down.example.com/")
    slow = await fetcher.fetch("https://slow.example.com/")
    assert down.error and "ConnectError" in down.error and down.status is None
    assert slow.error and "timeout" in slow.error


async def test_dns_failure_is_an_error(fake_dns):
    fake_dns.records["nx.example.com"] = []
    result = await make_fetcher().fetch("https://nx.example.com/")
    assert result.error and result.error.startswith("dns resolution failed")
    assert result.blocked is None


@respx.mock
async def test_binary_content_is_not_decoded():
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    respx.get("https://example.com/doc.pdf").mock(
        return_value=httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    )
    result = await make_fetcher().fetch("https://example.com/doc.pdf")
    assert result.ok and result.content == pdf and result.text is None


@respx.mock
async def test_http_error_statuses_are_results_not_exceptions():
    respx.get(PAGE).mock(
        return_value=httpx.Response(503, text="Service Unavailable", headers={"content-type": "text/html"})
    )
    result = await make_fetcher().fetch(PAGE)
    assert (
        result.status == 503
        and not result.ok
        and result.error is None
        and result.text == "Service Unavailable"
    )


# --------------------------------------------------------------------------- robots.txt


@respx.mock
async def test_robots_disallow_blocks_without_fetching_the_page():
    robots = respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: SignalLensBot\nDisallow: /pricing/\n",
            headers={"content-type": "text/plain"},
        )
    )
    page = respx.get(PAGE).mock(return_value=httpx.Response(200, text="page"))
    fetcher = make_fetcher(respect_robots=True)
    result = await fetcher.fetch(PAGE)
    assert result.blocked == "robots"
    assert robots.call_count == 1 and not page.called
    # check_robots=False (e.g. archive captures) bypasses the policy
    assert (await fetcher.fetch(PAGE, check_robots=False)).ok


@respx.mock
async def test_robots_5xx_disallows_and_404_allows():
    respx.get("https://a.example.com/robots.txt").mock(return_value=httpx.Response(500))
    respx.get("https://b.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://b.example.com/x").mock(return_value=httpx.Response(200, text="ok"))
    fetcher = make_fetcher(respect_robots=True)
    assert (await fetcher.fetch("https://a.example.com/x")).blocked == "robots"
    assert (await fetcher.fetch("https://b.example.com/x")).ok


@respx.mock
async def test_respect_robots_false_never_fetches_robots():
    robots = respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    )
    respx.get(PAGE).mock(return_value=httpx.Response(200, text="page"))
    assert (await make_fetcher(respect_robots=False).fetch(PAGE)).ok
    assert not robots.called


# --------------------------------------------------------------------------- politeness


@respx.mock
async def test_requests_to_the_same_host_are_spaced():
    respx.get(url__regex=r"https://example\.com/p\d").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("https://other.example.org/").mock(return_value=httpx.Response(200, text="ok"))
    fetcher = make_fetcher(min_host_interval_s=0.25)
    await fetcher.fetch("https://example.com/p1")
    started = time.perf_counter()
    await fetcher.fetch("https://other.example.org/")  # different host: no wait
    assert time.perf_counter() - started < 0.2
    await fetcher.fetch("https://example.com/p2")  # same host: waits out the interval
    assert time.perf_counter() - started >= 0.2


# --------------------------------------------------------------------------- sandbox


async def test_sandbox_scheme_uses_resolver_without_network():
    seen = []

    async def resolver(slug):
        seen.append(slug)
        if slug == "acme-pricing":
            return "<main><h1>Acme pricing</h1><p>Plans from ₹999</p></main>", "Acme Pricing"
        return None

    fetcher = make_fetcher(sandbox_resolver=resolver)
    ok = await fetcher.fetch("sandbox://acme-pricing")
    missing = await fetcher.fetch("sandbox://nope")
    assert ok.ok and ok.from_sandbox and ok.status == 200
    assert ok.content_type.startswith("text/html")
    assert "<title>Acme Pricing</title>" in ok.text and "₹999" in ok.text
    assert ok.content == ok.text.encode("utf-8")
    assert missing.status == 404 and missing.from_sandbox and not missing.ok
    assert seen == ["acme-pricing", "nope"]


async def test_sandbox_without_resolver_or_with_failing_resolver():
    assert (await make_fetcher().fetch("sandbox://x")).blocked == "unsupported_scheme"

    async def broken(slug):
        raise RuntimeError("db down")

    result = await make_fetcher(sandbox_resolver=broken).fetch("sandbox://x")
    assert result.error and "db down" in result.error


# --------------------------------------------------------------------------- decoding


def test_decode_uses_header_charset_then_meta_then_utf8():
    assert decode_body("café".encode(), "text/html; charset=utf-8") == "café"
    cp1252 = '<html><head><meta charset="windows-1252"></head><body>Price: € 5 – café</body></html>'.encode(
        "cp1252"
    )
    assert "€ 5 – café" in decode_body(cp1252, "text/html")
    http_equiv = b'<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><p>caf\xe9 \x93quoted\x94</p>'
    assert "café “quoted”" in decode_body(http_equiv, "text/html")  # latin-1 label decodes as windows-1252
    assert decode_body("naïve".encode(), None) == "naïve"
    assert decode_body(b"\xff\xfeh\x00i\x00", "text/plain") == "hi"  # UTF-16 BOM
    assert decode_body(b"bad \xff byte", "text/plain; charset=utf-8") == "bad � byte"
    assert decode_body(b"%PDF-1.7 ...", "application/pdf") is None
    assert decode_body(b'{"a": 1}', "application/json") == '{"a": 1}'
    assert decode_body(b"x", "text/html; charset=no-such-codec") == "x"
