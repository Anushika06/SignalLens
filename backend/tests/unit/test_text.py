import time

import pytest

from signallens.util.text import (
    mask_volatile,
    normalize_for_match,
    normalize_ws,
    quote_in_text,
    sha256_text,
    truncate,
    window_around,
)


def test_normalize_ws_collapses_and_applies_nfkc():
    assert normalize_ws("  Start accepting \n\t payments  ") == "Start accepting payments"
    assert normalize_ws("ﬁle") == "file"  # NFKC ligature


def test_sha256_text_is_hex_and_stable():
    digest = sha256_text("abc")
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


class TestMaskVolatile:
    @pytest.mark.parametrize(
        "volatile",
        [
            "2026-09-28",
            "2026-09-28T10:15:00Z",
            "2026-09-28 10:15:00+05:30",
            "Sep 28, 2026",
            "Sept. 28th, 2026",
            "28 September 2026",
            "28th of September, 2026",
            "Mon, Sep 28",
            "28/09/2026",
            "28.09.2026",
            "10:15 AM",
            "22:04:11",
            "7pm",
            "3 minutes ago",
            "2 hrs ago",
            "an hour ago",
            "5m ago",
            "yesterday",
            "just now",
            "© 2026",
            "Copyright 2019-2026",
            "Copyright © 2019 – 2026",
            "(c) 2025",
        ],
    )
    def test_volatile_tokens_are_masked(self, volatile):
        masked = mask_volatile(f"Updated {volatile} here")
        assert volatile not in masked
        assert masked.startswith("Updated <") and masked.endswith("> here")

    def test_ids_and_cache_busters(self):
        assert mask_volatile("session a8Fk2LmQ9zX7pR3t end") == "session <ID> end"
        assert mask_volatile("req 550e8400-e29b-41d4-a716-446655440000") == "req <ID>"
        assert mask_volatile("etag deadbeefcafebabe1234") == "etag <ID>"
        assert mask_volatile("/static/app.js?v=123") == "/static/app.js?v=<CB>"
        assert mask_volatile("style.css?ver=1.2.3&x=1") == "style.css?ver=<CB>&x=1"

    @pytest.mark.parametrize(
        "stable",
        [
            "Start accepting payments at just 2%",
            "₹2499 per month",
            "40,000+ businesses",
            "1.8% per transaction",
            "0%* platform fees for first 90 days",
            "Settlement in 2 days",
            "T+2 settlements",
            "24x7 support",
            "ratio 1:10",
            "March 2026 launch",
            "state-of-the-art-2026-edition",
            "internationalization",
            "Top 10 marketing tips",
        ],
    )
    def test_prices_percentages_and_counts_are_never_masked(self, stable):
        assert mask_volatile(stable) == stable

    def test_masking_makes_date_only_edits_identical(self):
        a = mask_volatile("Last updated: Sep 28, 2026 at 10:15 AM. © 2026 Razorpay")
        b = mask_volatile("Last updated: Oct 1, 2026 at 9:05 PM. © 2027 Razorpay")
        assert a == b


def test_normalize_for_match_unifies_typography():
    raw = "“Zero​-fee” — it’s FREE"
    assert normalize_for_match(raw) == '"zero-fee" - it\'s free'


class TestQuoteInText:
    TEXT = (
        "Start accepting payments at just 2% per transaction. "
        "0%* platform fees for first 90 days for new merchants. "
        "Razorpay does not charge setup fees or annual maintenance charges. "
        "Trusted by 40,000+ businesses across India."
    )

    def test_exact_quote(self):
        assert quote_in_text("Start accepting payments at just 2%", self.TEXT)

    def test_typography_and_case_differences_pass(self):
        assert quote_in_text("RAZORPAY DOES NOT CHARGE SETUP FEES", self.TEXT)
        assert quote_in_text("Razorpay does not charge setup fees", self.TEXT)

    def test_small_extraction_differences_pass_fuzzily(self):
        assert quote_in_text("Start accepting payments at just 2 % per transaction", self.TEXT)
        assert quote_in_text("0% platform fees for the first 90 days for new merchants", self.TEXT)

    def test_changed_number_fails(self):
        assert not quote_in_text("Start accepting payments at just 1.8%", self.TEXT)
        assert not quote_in_text("Start accepting payments at just 1.8% per transaction", self.TEXT)
        assert not quote_in_text("0%* platform fees for first 60 days for new merchants", self.TEXT)
        assert not quote_in_text("Trusted by 50,000+ businesses across India", self.TEXT)

    def test_dropped_negation_fails(self):
        assert not quote_in_text("Razorpay does charge setup fees or annual maintenance charges", self.TEXT)

    def test_invented_sentence_fails(self):
        assert not quote_in_text(
            "Razorpay will raise prices for enterprise merchants next quarter", self.TEXT
        )

    def test_short_quotes_must_match_exactly(self):
        assert quote_in_text("just 2%", self.TEXT)
        assert not quote_in_text("just 3%", self.TEXT)
        assert not quote_in_text("", self.TEXT)

    def test_thousands_separators_are_equivalent(self):
        assert quote_in_text("Trusted by 40000+ businesses across India", self.TEXT)

    def test_elided_quote_needs_every_part(self):
        assert quote_in_text("Start accepting payments ... 0%* platform fees for first 90 days", self.TEXT)
        assert not quote_in_text("Start accepting payments ... 5% platform fees for first 90 days", self.TEXT)

    def test_fast_on_large_documents(self):
        filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 5000  # ~285k chars
        text = filler + self.TEXT + filler
        started = time.perf_counter()
        assert quote_in_text("Start accepting payments at just 2 % per transaction", text)
        assert not quote_in_text("Start accepting payments at just 1.8% per transaction", text)
        assert not quote_in_text("An entirely invented statement about quarterly revenue growth", text)
        assert time.perf_counter() - started < 1.0


def test_truncate():
    assert truncate("hello", 10) == "hello"
    assert truncate("hello world", 8) == "hello w…"
    assert len(truncate("a" * 50, 10)) == 10
    assert truncate("hello", 0) == ""
    assert truncate("hello world", 8, marker="...") == "hello..."


class TestWindowAround:
    def test_windows_around_matches_are_merged_and_separated(self):
        text = ("aaa " * 300) + "Razorpay pricing 2% " + ("bbb " * 300) + "new PRICING note " + ("ccc " * 300)
        out = window_around(text, ["pricing"], radius=20)
        parts = out.split("\n…\n")
        assert len(parts) == 2
        assert "Razorpay pricing 2%" in parts[0]
        assert "new PRICING note" in parts[1]

    def test_overlapping_windows_merge(self):
        text = "x " * 200 + "fee one fee two fee three" + " y" * 200
        out = window_around(text, ["fee"], radius=30)
        assert "\n…\n" not in out
        assert "fee one fee two fee three" in out

    def test_no_match_returns_head(self):
        text = "abcdefghij" * 1000
        assert window_around(text, ["zzz"], max_chars=50) == truncate(text, 50)

    def test_respects_max_chars(self):
        text = " ".join(f"term{i} filler words here" for i in range(2000))
        out = window_around(text, ["term"], radius=100, max_chars=500)
        assert len(out) <= 500
