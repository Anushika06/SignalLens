import asyncio

import pytest

from signallens.fetch.robots import RobotsPolicy, product_token

UA = "SignalLensBot/0.1 (+https://signallens.example/bot)"

ROBOTS = """
User-agent: *
Disallow: /admin
Disallow: /
Allow: /pricing
Allow: /$
Disallow: /*.pdf$
Crawl-delay: 4

User-agent: SignalLensBot
Disallow: /private
Allow: /private/press
Disallow: /*?session=
Crawl-delay: 2

User-agent: OtherBot
Disallow: /
"""


class FakeFetch:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    async def __call__(self, url):
        self.calls.append(url)
        await asyncio.sleep(0)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def test_product_token():
    assert product_token(UA) == "SignalLensBot"
    assert product_token("Mozilla/5.0 (compatible)") == "Mozilla"


async def test_group_for_our_token_and_rfc9309_matching():
    fetch = FakeFetch([(200, ROBOTS)])
    robots = RobotsPolicy(fetch, UA)
    assert await robots.allowed("https://example.com/pricing")
    assert not await robots.allowed("https://example.com/private/team")
    assert await robots.allowed("https://example.com/private/press/2026")  # longest match wins
    assert not await robots.allowed("https://example.com/search?session=abc")  # wildcard
    assert await robots.allowed("https://example.com/search?q=abc")
    assert await robots.crawl_delay("https://example.com/") == 2.0
    assert fetch.calls == ["https://example.com/robots.txt"]  # cached per origin


async def test_default_group_longest_match_and_end_anchor():
    robots = RobotsPolicy(FakeFetch([(200, ROBOTS)]), "SomeOtherCrawler/1.0")
    assert await robots.allowed("https://example.com/pricing/")  # Allow: /pricing beats Disallow: /
    assert await robots.allowed("https://example.com/")  # Allow: /$
    assert not await robots.allowed("https://example.com/about")
    assert not await robots.allowed("https://example.com/docs/guide.pdf")  # /*.pdf$ beats Disallow: /
    assert not await robots.allowed(
        "https://example.com/docs/guide.pdf?x=1"
    )  # "$" fails; "Disallow: /" applies
    assert await robots.allowed(
        "https://example.com/pricing/rates.pdf"
    )  # "/pricing" (8) outranks "/*.pdf$" (7)
    assert await robots.crawl_delay("https://example.com/") == 4.0


async def test_404_allows_everything():
    robots = RobotsPolicy(FakeFetch([(404, "<html>not found</html>")]), UA)
    assert await robots.allowed("https://example.com/anything")
    assert await robots.crawl_delay("https://example.com/") is None


@pytest.mark.parametrize("response", [(500, "oops"), (503, None), (None, None), RuntimeError("boom")])
async def test_server_errors_and_network_failures_disallow_everything(response):
    robots = RobotsPolicy(FakeFetch([response]), UA)
    assert not await robots.allowed("https://example.com/pricing")


async def test_disallow_expires_after_ttl():
    now = [1000.0]
    fetch = FakeFetch([(503, None), (200, "User-agent: *\nDisallow: /private\n")])
    robots = RobotsPolicy(fetch, UA, ttl_s=60, clock=lambda: now[0])
    assert not await robots.allowed("https://example.com/pricing")
    now[0] += 30
    assert not await robots.allowed("https://example.com/pricing")
    assert len(fetch.calls) == 1
    now[0] += 31
    assert await robots.allowed("https://example.com/pricing")
    assert len(fetch.calls) == 2


async def test_cache_is_per_origin():
    fetch = FakeFetch([(200, "User-agent: *\nDisallow: /\n")])
    robots = RobotsPolicy(fetch, UA)
    await robots.allowed("https://a.example.com/x")
    await robots.allowed("https://a.example.com/y")
    await robots.allowed("http://a.example.com/x")
    await robots.allowed("https://b.example.com/x")
    assert fetch.calls == [
        "https://a.example.com/robots.txt",
        "http://a.example.com/robots.txt",
        "https://b.example.com/robots.txt",
    ]


async def test_one_fetch_in_flight_per_host():
    fetch = FakeFetch([(200, "User-agent: *\nAllow: /\n")])
    robots = RobotsPolicy(fetch, UA)
    results = await asyncio.gather(*(robots.allowed(f"https://example.com/p{i}") for i in range(10)))
    assert all(results)
    assert len(fetch.calls) == 1


async def test_malformed_url_is_refused():
    robots = RobotsPolicy(FakeFetch([(200, "")]), UA)
    assert not await robots.allowed("not a url")
