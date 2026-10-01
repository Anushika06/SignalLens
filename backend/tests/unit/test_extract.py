from datetime import UTC, datetime

import pytest

from signallens.fetch.extract import (
    ExtractedDoc,
    assess_quality,
    extract_article,
    extract_page,
    extract_pdf,
    extract_result,
)
from signallens.fetch.http import FetchResult

PRICING_URL = "https://razorpay.com/pricing/"


def _texts(doc: ExtractedDoc) -> list[str]:
    return [b.text for b in doc.blocks]


def _fetch_result(
    body: bytes | str, content_type: str | None = "text/html; charset=utf-8", status: int = 200, **kw
):
    content = body.encode("utf-8") if isinstance(body, str) else body
    text = body if isinstance(body, str) else None
    fields = {
        "url": PRICING_URL,
        "final_url": PRICING_URL,
        "status": status,
        "content_type": content_type,
        "content": content,
        "text": text,
        "etag": None,
        "last_modified": None,
        "not_modified": False,
        "elapsed_ms": 5,
    }
    fields.update(kw)
    return FetchResult(**fields)


def _make_pdf(lines: list[str], *, title: str | None = None, created: str | None = None) -> bytes:
    """A tiny valid one-page PDF (Helvetica text), optionally with /Title and /CreationDate."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT", "/F1 11 Tf", "72 740 Td"]
    for line in lines:
        ops += [f"({esc(line)}) Tj", "0 -14 Td"]
    stream = "\n".join([*ops, "ET"]).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    info = ""
    if title or created:
        entries = ([f"/Title ({esc(title)})"] if title else []) + (
            [f"/CreationDate ({created})"] if created else []
        )
        objects.append(("<< " + " ".join(entries) + " >>").encode("latin-1"))
        info = f" /Info {len(objects)} 0 R"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R{info} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# --------------------------------------------------------------------------- monitored pages


class TestPricingPage:
    @pytest.fixture
    def doc(self, fixture_text):
        return extract_page(fixture_text("pricing_page.html"), PRICING_URL)

    def test_metadata(self, doc):
        assert doc.title == "Pricing | Razorpay Payment Gateway"
        assert doc.canonical_url == "https://razorpay.com/pricing/"  # made absolute
        assert doc.description.startswith("Transparent pricing")
        assert doc.lang == "en-IN" and doc.kind == "html"
        assert doc.quality == "ok" and doc.quality_reason is None and doc.challenge is None

    def test_every_price_token_survives(self, doc):
        texts = _texts(doc)
        assert "Start accepting payments at just 2%" in texts
        assert "0%* platform fees for first 90 days" in texts
        assert "2% per transaction" in texts  # adjacent spans get a separating space
        assert "₹2499/month" in texts  # ...but never inside a price
        assert "Domestic credit and debit cards | 2%" in texts
        assert "International cards | 3%" in texts  # a <div> inside the cell stays in the row
        assert "UPI | 0%" in texts
        assert "Instant settlements | Not included | Included" in texts  # icon labels kept
        assert any("40,000+ businesses" in t for t in texts)

    def test_block_kinds_in_document_order(self, doc):
        kinds = {b.text: b.kind for b in doc.blocks}
        assert kinds["Start accepting payments at just 2%"] == "heading"
        assert (
            kinds["No setup fees. No annual maintenance charges. Pay only for what you use."] == "paragraph"
        )
        assert kinds["100+ payment methods"] == "list_item"
        assert kinds["Payment method | Fee"] == "table_row"
        assert kinds["0%* platform fees for first 90 days"] == "other"
        texts = _texts(doc)
        assert texts.index("Standard Plan") < texts.index("Enterprise Plan") < texts.index("UPI | 0%")

    @pytest.mark.parametrize(
        "boilerplate",
        [
            "Skip to content",
            "cookies",
            "Accept All",
            "Payroll",
            "Banking",
            "Sign Up",
            "Home",
            "Talk to sales",
            "newsletter",
            "Need help",
            "All rights reserved",
            "Privacy",
        ],
    )
    def test_boilerplate_is_removed(self, doc, boilerplate):
        assert boilerplate.lower() not in doc.text.lower()

    def test_text_and_word_count(self, doc):
        assert doc.text == "\n".join(_texts(doc))
        assert doc.word_count == len(doc.text.split())

    def test_hash_ignores_volatile_edits_but_not_price_edits(self, fixture_text):
        html = fixture_text("pricing_page.html")
        base = extract_page(html, PRICING_URL).content_hash
        volatile = html.replace("Sep 28, 2026", "Oct 2, 2026").replace(
            "© 2026 Razorpay Software", "© 2027 Razorpay Software"
        )
        assert volatile != html
        assert extract_page(volatile, PRICING_URL).content_hash == base
        price = html.replace('<span class="highlight">2%</span>', '<span class="highlight">1.8%</span>')
        assert extract_page(price, PRICING_URL).content_hash != base


def test_header_with_hero_copy_is_kept_but_nav_header_dropped():
    html = """<html><body>
      <header class="top"><a href="/">Logo</a><a href="/a">Products</a><a href="/b">Company</a></header>
      <header class="hero"><nav><a href="/x">Docs</a></nav>
        <h1>Payments at just 2%</h1><p>Zero setup fees for every new business on the platform.</p></header>
      <main><p>Body copy that describes the product in enough words to be a real page.</p></main>
    </body></html>"""
    texts = _texts(extract_page(html))
    assert "Payments at just 2%" in texts
    assert "Zero setup fees for every new business on the platform." in texts
    assert not any("Products" in t or "Docs" in t for t in texts)


def test_menu_classes_are_dropped_only_when_link_dense():
    html = """<html><body>
      <ul class="main-menu"><li><a href="/1">Pricing</a></li><li><a href="/2">Careers</a></li></ul>
      <div class="menu-item"><h3>Paneer Tikka</h3><span>₹299</span></div>
    </body></html>"""
    texts = _texts(extract_page(html))
    assert "Paneer Tikka" in texts and "₹299" in texts
    assert "Careers" not in " ".join(texts)


def test_wrapper_with_boilerplate_looking_class_does_not_swallow_the_page():
    words = " ".join(f"word{i}" for i in range(80))
    html = f'<html><body><div class="nav-open"><h1>Pricing 2%</h1><p>{words}</p></div></body></html>'
    assert "Pricing 2%" in _texts(extract_page(html))


def test_inline_joining_rules():
    html = """<html><body>
      <div><span>Starting at</span><span>₹2,499</span></div>
      <div><span>₹</span><span>2499</span><span>/mo</span></div>
      <div><span>2</span><span>.5%</span></div>
      <div>Fast.<b>Secure</b></div>
      <p>Line one<br>line two</p>
    </body></html>"""
    texts = _texts(extract_page(html))
    assert texts == ["Starting at ₹2,499", "₹2499/mo", "2.5%", "Fast. Secure", "Line one line two"]


def test_separator_only_blocks_are_dropped_but_footnote_marks_kept():
    html = "<html><body><p>Banking</p><p>|</p><p>Payroll</p><p>•</p><div>*</div></body></html>"
    assert _texts(extract_page(html)) == ["Banking", "Payroll", "*"]


def test_consecutive_duplicates_are_dropped_and_nested_lists_split():
    html = """<html><body>
      <div class="desktop">Free for 90 days</div><div class="mobile">Free for 90 days</div>
      <ul><li>Cards<ul><li>Visa</li><li>RuPay</li></ul></li><li>UPI</li></ul>
    </body></html>"""
    doc = extract_page(html)
    assert _texts(doc) == ["Free for 90 days", "Cards", "Visa", "RuPay", "UPI"]
    assert all(b.kind == "list_item" for b in doc.blocks[1:])


def test_layout_tables_are_not_flattened_into_one_row():
    html = """<html><body><table><tr>
      <td><h2>Plans</h2><table><tr><td>Basic</td><td>2%</td></tr></table></td>
    </tr></table></body></html>"""
    texts = _texts(extract_page(html))
    assert "Plans" in texts and "Basic | 2%" in texts


def test_empty_or_garbage_html_is_degenerate_not_an_exception():
    for html in ["", "   ", "<html></html>"]:
        doc = extract_page(html)
        assert doc.quality == "degenerate" and doc.blocks == []


def test_published_time_meta_is_read():
    html = '<html><head><meta property="article:published_time" content="2026-09-21T10:15:00+05:30"></head><body>x</body></html>'
    assert extract_page(html).published_at == datetime(2026, 9, 21, 4, 45, tzinfo=UTC)


# --------------------------------------------------------------------------- articles


def test_article_extraction(fixture_text):
    doc = extract_article(fixture_text("news_article.html"), "https://www.economicledger.example/tech/x")
    texts = _texts(doc)
    assert doc.title.startswith("Razorpay raises $375 million")
    assert doc.published_at == datetime(2026, 9, 21, 4, 45, tzinfo=UTC)
    assert doc.canonical_url.endswith("/articleshow/12345.cms")
    assert all(b.kind == "paragraph" for b in doc.blocks)
    assert any(t.startswith("Bengaluru-based payments company Razorpay said on Monday") for t in texts)
    assert any("not planning an IPO this year" in t for t in texts)
    joined = "\n".join(texts)
    for noise in ("Markets", "Advertisement", "Also read", "morning briefing", "All rights reserved"):
        assert noise not in joined
    assert doc.quality == "ok"


def test_article_falls_back_to_page_extraction():
    html = "<html><head><title>Rates</title></head><body><div><span>UPI</span> <span>0%</span></div></body></html>"
    doc = extract_article(html)
    assert _texts(doc) == ["UPI 0%"] and doc.title == "Rates"


# --------------------------------------------------------------------------- quality gate


def test_cloudflare_challenge_is_blocked(fixture_text):
    doc = extract_page(fixture_text("cloudflare_challenge.html"), PRICING_URL)
    assert doc.quality == "blocked" and "Just a moment" in doc.quality_reason
    result = extract_result(_fetch_result(fixture_text("cloudflare_challenge.html"), status=200))
    assert result.quality == "blocked"


def test_small_page_with_captcha_markup_is_blocked_but_real_pages_with_recaptcha_are_not(fixture_text):
    datadome = (
        "<html><head><title>razorpay.com</title></head><body><p>Please enable JS and disable any ad blocker</p>"
        '<iframe src="https://geo.captcha-delivery.com/captcha/?initialCid=abc"></iframe></body></html>'
    )
    assert extract_page(datadome).quality == "blocked"
    assert extract_page(fixture_text("pricing_page.html")).quality == "ok"  # it loads recaptcha/api.js


def test_article_about_captchas_is_not_blocked():
    words = " ".join(["Researchers found that captcha systems and access denied pages frustrate users."] * 30)
    html = f"<html><head><title>Why captchas fail</title></head><body><article><p>{words}</p></article></body></html>"
    assert extract_page(html).quality == "ok"


def _doc(words: int, title: str | None = "Page") -> ExtractedDoc:
    doc = extract_page("<html><body><p>" + " ".join(["word"] * words) + "</p></body></html>")
    doc.title = title
    return doc


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_blocking_statuses(status):
    assert assess_quality(_doc(300), http_status=status) == ("blocked", f"HTTP {status}")


def test_error_status_is_degenerate():
    quality, reason = assess_quality(_doc(300), http_status=404)
    assert quality == "degenerate" and "404" in reason


def test_too_few_words_is_degenerate():
    quality, reason = assess_quality(_doc(12), http_status=200)
    assert quality == "degenerate" and "12 words" in reason


def test_reference_word_count_catches_shrunken_pages():
    assert assess_quality(_doc(300), http_status=200, reference_word_count=1000)[0] == "degenerate"
    assert assess_quality(_doc(400), http_status=200, reference_word_count=1000) == ("ok", None)
    assert assess_quality(_doc(300), http_status=200) == ("ok", None)


# --------------------------------------------------------------------------- PDFs


PDF_LINES = [
    "RBI Circular: Payment Aggregators - Settlement Timelines",
    "Payment aggregators shall settle funds to merchants within one business day of the transaction.",
    "Aggregators must maintain an escrow account with a scheduled commercial bank for all merchant funds.",
    "This circular is effective from October 1, 2026 and applies to all authorised payment aggregators.",
]


def test_pdf_extraction():
    doc = extract_pdf(
        _make_pdf(PDF_LINES, title="RBI/2026-27/112 Payment Aggregators", created="D:20260921101500+05'30'")
    )
    assert doc.kind == "pdf" and doc.quality == "ok"
    assert doc.title == "RBI/2026-27/112 Payment Aggregators"
    assert doc.published_at == datetime(2026, 9, 21, 4, 45, tzinfo=UTC)
    assert "settle funds to merchants within one business day" in doc.text
    assert "effective from October 1, 2026" in doc.text


def test_pdf_title_falls_back_to_first_line():
    doc = extract_pdf(_make_pdf(PDF_LINES))
    assert doc.title.startswith("RBI Circular: Payment Aggregators")


def test_corrupt_pdf_is_degenerate():
    doc = extract_pdf(b"%PDF-1.4 this is not really a pdf")
    assert doc.quality == "degenerate" and doc.blocks == []


# --------------------------------------------------------------------------- dispatcher


def test_extract_result_dispatches_on_content_type(fixture_text):
    html = fixture_text("pricing_page.html")
    page = extract_result(_fetch_result(html))
    assert page.kind == "html" and "UPI | 0%" in _texts(page)

    article = extract_result(_fetch_result(fixture_text("news_article.html")), mode="article")
    assert all(b.kind == "paragraph" for b in article.blocks)

    pdf = extract_result(_fetch_result(_make_pdf(PDF_LINES, title="Circular"), "application/pdf"))
    assert pdf.kind == "pdf" and pdf.title == "Circular"

    as_json = extract_result(_fetch_result('{"plans": {"standard": {"fee": "2%"}}}', "application/json"))
    assert as_json.kind == "json" and '"fee": "2%"' in as_json.text

    plain = extract_result(_fetch_result("First para.\n\nSecond para.", "text/plain"))
    assert plain.kind == "text" and _texts(plain) == ["First para.", "Second para."]

    xml = extract_result(
        _fetch_result(
            "<rss><channel><item><title>Rate cut</title></item></channel></rss>", "application/rss+xml"
        )
    )
    assert xml.kind == "xml" and "Rate cut" in xml.text

    unknown = extract_result(_fetch_result(b"\x89PNG\r\n", "image/png"))
    assert unknown.quality == "degenerate" and "image/png" in unknown.quality_reason


def test_extract_result_quality_uses_status_and_reference(fixture_text):
    html = fixture_text("pricing_page.html")
    assert extract_result(_fetch_result(html, status=403)).quality == "blocked"
    doc = extract_result(_fetch_result(html), reference_word_count=10_000)
    assert doc.quality == "degenerate" and "35%" in doc.quality_reason


def test_extract_result_for_failed_fetches():
    blocked = extract_result(_fetch_result(b"", None, status=None, blocked="robots"))
    assert blocked.quality == "blocked" and "robots" in blocked.quality_reason
    failed = extract_result(_fetch_result(b"", None, status=None, error="timeout after 20s"))
    assert failed.quality == "degenerate" and "timeout" in failed.quality_reason
    not_modified = extract_result(_fetch_result(b"", None, status=304, not_modified=True))
    assert not_modified.quality == "degenerate" and "304" in not_modified.quality_reason
