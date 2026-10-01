"""JavaScript rendering: shell detection, the pipeline helper (with a fake renderer) and,
when Playwright + Chromium are installed, a real headless render with the request guard."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from signallens.fetch.extract import extract_result
from signallens.fetch.http import FetchResult
from signallens.fetch.render import (
    DISABLED_REASON,
    RENDERED_NOTE,
    RenderBlocked,
    RenderResult,
    RenderUnavailable,
    close_renderer,
    js_shell_reason,
    render_availability,
    render_if_js_shell,
    render_page,
)

SHELL = """<!doctype html><html><head><title>Acme</title>
<script src="/static/js/main.4f2a.js" defer></script></head>
<body><noscript>You need to enable JavaScript to run this app.</noscript><div id="root"></div></body></html>"""

RENDERED = ("<html><head><title>Acme pricing</title></head><body><div id='root'><h1>Pricing</h1>"
            + "".join(f"<p>Plan {i} costs {i * 10} dollars per month and includes unlimited projects.</p>"
                      for i in range(1, 6))
            + "</div></body></html>")


def fetched(html: str, *, url: str = "https://acme.example/pricing", status: int = 200,
            sandbox: bool = False) -> FetchResult:
    return FetchResult(url=url, final_url=url, status=status, content_type="text/html; charset=utf-8",
                       content=html.encode(), text=html, etag='"abc"', last_modified=None, not_modified=False,
                       elapsed_ms=1, from_sandbox=sandbox)


def test_detects_an_empty_javascript_shell():
    fr = fetched(SHELL)
    doc = extract_result(fr)
    assert doc.quality == "degenerate"
    reason = js_shell_reason(fr, doc)
    assert reason and "JavaScript shell" in reason and "mount point" in reason


def test_next_style_shell_without_noscript():
    html = ('<html><head><script src="/_next/static/chunks/a.js"></script></head><body><div id="__next"></div>'
            '<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script></body></html>')
    fr = fetched(html)
    assert js_shell_reason(fr, extract_result(fr))


def test_never_treats_a_bot_challenge_as_a_shell(fixture_text):
    fr = fetched(fixture_text("cloudflare_challenge.html"))
    doc = extract_result(fr)
    assert doc.quality == "blocked"
    assert js_shell_reason(fr, doc) is None
    # A script-heavy page that mentions a captcha is not rendered either.
    html = SHELL.replace("<div id=\"root\"></div>", "<div id=\"root\"></div><div class=\"g-recaptcha\"></div>")
    fr = fetched(html)
    assert js_shell_reason(fr, extract_result(fr)) is None


def test_not_a_shell():
    tiny = fetched("<html><body><p>Hello there.</p></body></html>")  # no scripts: just a tiny page
    assert js_shell_reason(tiny, extract_result(tiny)) is None
    full = fetched(RENDERED)
    assert extract_result(full).quality == "ok" and js_shell_reason(full, extract_result(full)) is None
    err = fetched(SHELL, status=500)
    assert js_shell_reason(err, extract_result(err)) is None
    sandbox = fetched(SHELL, sandbox=True)
    assert js_shell_reason(sandbox, extract_result(sandbox)) is None


async def test_disabled_keeps_skip_behaviour_with_clear_reason():
    fr = fetched(SHELL)
    out = await render_if_js_shell(fr, extract_result(fr), enabled=False, timeout_s=5, user_agent="t")
    assert not out.rendered and out.doc.quality == "degenerate"
    assert out.doc.quality_reason == DISABLED_REASON == "needs JavaScript rendering (disabled on this deployment)"


async def test_enabled_renders_and_reextracts():
    calls = []

    async def fake_renderer(url, **kw):
        calls.append((url, kw))
        return RenderResult(html=RENDERED, final_url=url, status=200)

    fr = fetched(SHELL)
    out = await render_if_js_shell(fr, extract_result(fr), enabled=True, timeout_s=7, user_agent="UA",
                                   renderer=fake_renderer)
    assert out.rendered and out.note == RENDERED_NOTE and out.doc.quality == "ok"
    assert "Plan 3 costs 30 dollars" in out.doc.text
    assert out.fetch.text == RENDERED and out.fetch.etag is None  # validators of the shell are dropped
    assert calls[0][0] == fr.final_url and calls[0][1]["timeout_s"] == 7 and calls[0][1]["user_agent"] == "UA"


async def test_ok_pages_and_challenges_are_never_rendered(fixture_text):
    async def boom(url, **kw):  # pragma: no cover - must not be called
        raise AssertionError("renderer called")

    for html in (RENDERED, fixture_text("cloudflare_challenge.html")):
        fr = fetched(html)
        doc = extract_result(fr)
        out = await render_if_js_shell(fr, doc, enabled=True, timeout_s=5, user_agent="t", renderer=boom)
        assert not out.rendered and out.doc is doc


@pytest.mark.parametrize("error, expected", [
    (RenderUnavailable("Chromium is not installed (uv run playwright install chromium)"), "unavailable on this deployment"),
    (RenderBlocked("http://10.0.0.1/ is not a public address"), "not allowed"),
    (RuntimeError("crashed"), "headless browser failed"),
])
async def test_render_failures_keep_the_page_skipped(error, expected):
    async def failing(url, **kw):
        raise error

    fr = fetched(SHELL)
    out = await render_if_js_shell(fr, extract_result(fr), enabled=True, timeout_s=5, user_agent="t", renderer=failing)
    assert not out.rendered and out.doc.quality == "degenerate" and expected in out.doc.quality_reason
    assert out.doc.quality_reason.startswith("needs JavaScript rendering")


async def test_still_empty_after_rendering():
    async def same(url, **kw):
        return RenderResult(html=SHELL, final_url=url, status=200)

    fr = fetched(SHELL)
    out = await render_if_js_shell(fr, extract_result(fr), enabled=True, timeout_s=5, user_agent="t", renderer=same)
    assert out.rendered and out.doc.quality == "degenerate" and "still unusable" in out.doc.quality_reason


async def test_ssrf_policy_refuses_private_addresses_before_launching():
    with pytest.raises(RenderBlocked):
        await render_page("http://127.0.0.1:9/", timeout_s=2)
    with pytest.raises(RenderBlocked):
        await render_page("http://169.254.169.254/latest/meta-data/", timeout_s=2)


# --------------------------------------------------------------------------- real browser (optional)

available, detail = render_availability()
needs_browser = pytest.mark.skipif(not available, reason=f"JavaScript rendering unavailable: {detail}")

APP_PAGE = b"""<!doctype html><html><head><title>Shell</title></head><body><div id="root"></div>
<script>
  fetch('/data').then(r => r.json()).then(d => {
    document.getElementById('root').innerHTML = '<h1>' + d.title + '</h1>' + d.lines.map(l => '<p>' + l + '</p>').join('');
  });
  fetch('http://127.0.0.1:%d/secret').catch(() => {});      // another host: must be refused
  fetch('/bounce').catch(() => {});                         // redirects to that host: must be refused
  alert('dialogs are dismissed');
</script></body></html>"""


class _Servers:
    def __init__(self) -> None:
        self.hits: dict[str, list[str]] = {"public": [], "internal": []}
        outer = self

        def handler(label: str):
            class H(BaseHTTPRequestHandler):
                def do_GET(self):  # noqa: N802
                    outer.hits[label].append(self.path)
                    if label == "public" and self.path == "/":
                        body = APP_PAGE % outer.internal_port
                        self._send(200, body, "text/html")
                    elif label == "public" and self.path == "/data":
                        lines = [f"Plan {i} costs {i * 10} dollars per month with unlimited projects." for i in range(6)]
                        import json

                        self._send(200, json.dumps({"title": "Rendered pricing", "lines": lines}).encode(),
                                   "application/json")
                    elif label == "public" and self.path == "/bounce":
                        self.send_response(302)
                        self.send_header("Location", f"http://127.0.0.1:{outer.internal_port}/bounced")
                        self.end_headers()
                    else:
                        self._send(200, b"internal secret", "text/plain")

                def _send(self, status, body, ctype):
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            return H

        self.public = ThreadingHTTPServer(("127.0.0.1", 0), handler("public"))
        self.internal = ThreadingHTTPServer(("127.0.0.1", 0), handler("internal"))
        self.public_port = self.public.server_address[1]
        self.internal_port = self.internal.server_address[1]
        for srv in (self.public, self.internal):
            threading.Thread(target=srv.serve_forever, daemon=True).start()

    def close(self) -> None:
        for srv in (self.public, self.internal):
            srv.shutdown()
            srv.server_close()


@needs_browser
async def test_real_render_with_request_guard():
    servers = _Servers()
    public_origin = f"http://127.0.0.1:{servers.public_port}"

    async def only_public_server(url: str) -> bool:  # stands in for "public internet" in this test
        return url.startswith(public_origin + "/")

    try:
        try:
            result = await render_page(public_origin + "/", timeout_s=20, user_agent="SignalLensTest",
                                       url_policy=only_public_server)
        except RenderUnavailable as e:  # e.g. an event loop that cannot spawn the browser
            pytest.skip(str(e))
        doc = extract_result(fetched(result.html, url=result.final_url))
        assert doc.quality == "ok" and "Rendered pricing" in doc.text and "Plan 3 costs 30 dollars" in doc.text
        await asyncio.sleep(0.3)
        assert servers.hits["internal"] == []  # neither the direct request nor the redirect got through
        assert "/bounce" in servers.hits["public"] and result.blocked_requests >= 2
    finally:
        await close_renderer()
        servers.close()
