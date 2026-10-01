"""Text normalisation, volatile-token masking and evidence-quote verification.

* :func:`mask_volatile` is materiality tier 0 (C7): dates, clock times, "3 minutes ago",
  copyright years, session ids and cache-busting parameters change on every fetch without
  anything material happening, so they are replaced with stable placeholders before
  hashing and diffing. Prices, percentages and counts ("2%", "₹2499", "40,000+") are never
  touched - they are exactly what we monitor.
* :func:`quote_in_text` is the anti-hallucination check for evidence (C4): a quote only
  counts if it really occurs in a document we fetched. Near-misses that change a number or
  drop a negation are rejected even when they are otherwise similar.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from functools import lru_cache

from rapidfuzz import fuzz

__all__ = [
    "mask_volatile",
    "normalize_for_match",
    "normalize_ws",
    "quote_in_text",
    "sha256_text",
    "truncate",
    "window_around",
]


# --------------------------------------------------------------------------- basics


def normalize_ws(s: str) -> str:
    """Unicode NFKC, collapse every run of whitespace to one space, strip."""
    return " ".join(unicodedata.normalize("NFKC", s).split())


def sha256_text(s: str) -> str:
    """Hex SHA-256 of the UTF-8 encoding of ``s``."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def truncate(s: str, n: int, *, marker: str = "…") -> str:
    """Shorten ``s`` to at most ``n`` characters, ending with ``marker`` when cut."""
    if n <= 0:
        return ""
    if len(s) <= n:
        return s
    if n <= len(marker):
        return marker[:n]
    return s[: n - len(marker)].rstrip() + marker


# Invisible characters that break substring matching but carry no meaning.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​⁠﻿­‌‍"), None)
# fmt: off
_PUNCT_MAP = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
        "«": '"', "»": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
        "−": "-",
        " ": " ", " ": " ", " ": " ",
    }
)
# fmt: on


def normalize_for_match(s: str) -> str:
    """Canonical form for quote matching.

    Strips zero-width characters, unifies curly quotes, dashes and non-breaking spaces,
    applies NFKC, collapses whitespace and casefolds - so that copy/paste artefacts never
    decide whether a quote "exists".
    """
    s = s.translate(_ZERO_WIDTH).translate(_PUNCT_MAP)
    return normalize_ws(s).casefold()


# --------------------------------------------------------------------------- masking

_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?"
)
_WEEKDAY = (
    r"(?:(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?"
    r"|sat(?:urday)?|sun(?:day)?)\b\.?,?\s+)?"
)
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_CACHE_BUST_PARAMS = r"v|ver|version|rev|cb|cachebust|cache_bust|nocache|_|t|ts|timestamp"

# Order matters: the most specific patterns run first so later ones never see half a date.
_MASKS: list[tuple[re.Pattern[str], str]] = [
    # (c) 2026 / Copyright 2019-2026 / Copyright (c) 2019 - present
    (
        re.compile(
            r"(?:©|\(c\)|&copy;|\bcopyright\b)(?:\s*©)?\s*\d{4}(?:\s*[-–—]\s*(?:\d{4}|present))?",
            re.IGNORECASE,
        ),
        "<COPYRIGHT>",
    ),
    # ISO 8601 dates and datetimes: 2026-09-28, 2026-09-28T10:15:00Z, 2026-09-28 10:15:00+05:30
    (
        re.compile(
            r"\b\d{4}-\d{2}-\d{2}"
            r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:\s?(?:Z|[+-]\d{2}:?\d{2})\b)?)?"
        ),
        "<DATE>",
    ),
    # Sep 28, 2026 / September 28th 2026 / Mon, Sep 28
    (re.compile(rf"\b{_WEEKDAY}{_MONTH}\s+{_DAY}\b(?:,?\s+\d{{4}}\b)?", re.IGNORECASE), "<DATE>"),
    # 28 September 2026 / 28th of Sep, 2026 / Monday 28 Sep
    (re.compile(rf"\b{_WEEKDAY}{_DAY}\s+(?:of\s+)?{_MONTH}(?:,?\s+\d{{4}}\b)?", re.IGNORECASE), "<DATE>"),
    # 28/09/2026, 09-28-26, 28.09.2026, 2026/09/28
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-](?:\d{4}|\d{2})\b"), "<DATE>"),
    (re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"), "<DATE>"),
    (re.compile(r"\b\d{4}/\d{1,2}/\d{1,2}\b"), "<DATE>"),
    # 22:04:11 / 10:15 AM / 7pm / 10:15 (two-digit hour). "1:10" alone is left alone:
    # it is more often a ratio than a clock time.
    (re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d:[0-5]\d(?:[.,]\d+)?\b"), "<TIME>"),
    (re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\s?[ap]\.?m\b\.?", re.IGNORECASE), "<TIME>"),
    (re.compile(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b"), "<TIME>"),
    (re.compile(r"\b(?:1[0-2]|0?[1-9])\s?[ap]\.?m\b\.?", re.IGNORECASE), "<TIME>"),
    # 3 minutes ago / 2 hrs ago / an hour ago / 5m ago / yesterday / just now.
    # ("in 2 days" is deliberately NOT masked: "settlement in 2 days" is a product term.)
    (
        re.compile(
            r"\b(?:\d+|an?|one|two|three|few|several)\s*"
            r"(?:s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?|d|days?|w|wks?|weeks?"
            r"|mos?|months?|y|yrs?|years?)\s+ago\b",
            re.IGNORECASE,
        ),
        "<RELTIME>",
    ),
    (re.compile(r"\b(?:just now|moments? ago|a moment ago|yesterday)\b", re.IGNORECASE), "<RELTIME>"),
    # Cache-busting query values: ?v=123, &ver=1.2.3, ?_=1695..., ?cb=abc
    (
        re.compile(rf"(?<=[?&])({_CACHE_BUST_PARAMS})=[^&#\s\"'<>]*", re.IGNORECASE),
        r"\1=<CB>",
    ),
]

_ID_TOKEN = re.compile(r"(?<![\w+/=-])[A-Za-z0-9][\w+/=-]{14,}[\w=](?![\w+/=-])")
_HEX = re.compile(r"[0-9a-fA-F]{16,}")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _mask_id(match: re.Match[str]) -> str:
    """Mask tokens that look machine-generated: hex, UUIDs, or dense letter/digit mixes.

    A long word or slug ("state-of-the-art-2026") has few letter<->digit transitions;
    a session id or hash ("a8Fk2LmQ9zX7pR3t") has many.
    """
    token = match.group(0)
    if _UUID.fullmatch(token) or _HEX.fullmatch(token):
        return "<ID>"
    alnum = [c for c in token if c.isalnum()]
    digits = sum(c.isdigit() for c in alnum)
    if digits < 2 or len(alnum) - digits < 2:
        return token
    transitions = sum(1 for a, b in zip(alnum, alnum[1:], strict=False) if a.isdigit() != b.isdigit())
    return "<ID>" if transitions >= 4 else token


_DATE_NOISE_CONTEXT = re.compile(
    r"\b(?:updated|update|modified|published|posted|as\s+(?:of|on)|last|generated|reviewed|retrieved"
    r"|accessed|printed|refreshed|today)\b|©|\bcopyright\b",
    re.IGNORECASE,
)


def _dates_are_noise(s: str) -> bool:
    """Calendar dates are noise in "last updated / published / ©" lines and in date-only lines,
    but meaningful elsewhere ("Offer valid till 30 Sep 2026", "effective 1 October")."""
    if _DATE_NOISE_CONTEXT.search(s):
        return True
    stripped = s
    for pattern, replacement in _MASKS:
        if replacement == "<DATE>":
            stripped = pattern.sub("", stripped)
    return stripped != s and not re.sub(r"[\W_]+", "", stripped)


def mask_volatile(s: str, *, dates: bool | None = None) -> str:
    """Replace volatile tokens with stable placeholders so they never register as changes.

    Masks clock times, relative times ("3 minutes ago", "yesterday"), copyright notices,
    long hex/base64-like ids (>= 16 chars) and cache-busting parameters. Prices,
    percentages and counts are left intact.

    Calendar dates are context-dependent: with ``dates=None`` (default) they are masked
    only in "last updated / published / ©"-style lines and date-only lines, so an offer
    deadline or an effective date that changes still registers as a change. Pass
    ``dates=True`` or ``False`` to force either behaviour.
    """
    mask_dates = _dates_are_noise(s) if dates is None else dates
    for pattern, replacement in _MASKS:
        if replacement == "<DATE>" and not mask_dates:
            continue
        s = pattern.sub(replacement, s)
    return _ID_TOKEN.sub(_mask_id, s)


# --------------------------------------------------------------------------- quotes

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?")
_WORD = re.compile(r"\w+")
_NEGATIONS = frozenset({"not", "no", "never", "none", "nor", "neither", "without", "cannot"})
_MIN_FUZZY_LEN = 12
_SMALL_TEXT = 5_000
_MAX_ANCHOR_HITS = 200


@lru_cache(maxsize=8)
def _normalized_text(text: str) -> str:
    # A verifier usually checks several quotes against the same document.
    return normalize_for_match(text)


def _numbers(s: str) -> set[str]:
    out = set()
    for m in _NUMBER.finditer(s):
        tok = m.group(0)
        if _THOUSANDS.fullmatch(tok):  # 2,499 == 2499 ; 1,00,000 == 100000
            tok = tok.replace(",", "")
        out.add(tok)
    return out


def _negations(s: str) -> Counter[str]:
    words = _WORD.findall(s.replace("n't", " not"))
    return Counter(w for w in words if w in _NEGATIONS)


def _expand_to_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow an alignment so it never ends inside a word or number."""

    def inside_token(i: int) -> bool:
        c = text[i]
        if c.isalnum():
            return True
        # keep "1.8" / "2,499" whole when the alignment cut inside a number
        return c in ".," and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()

    while start > 0 and inside_token(start - 1):
        start -= 1
    while end < len(text) and inside_token(end):
        end += 1
    return start, end


def _candidate_windows(quote: str, text: str) -> list[tuple[int, int]]:
    """Regions of ``text`` worth fuzzy-matching against ``quote``.

    Scoring the whole of a 300k-character document is wasteful, so we anchor on the
    quote's rarest words that actually occur in the text (a hallucinated or misspelled
    word simply is not used as an anchor) and only score windows of +/- len(quote) around
    their occurrences. Small texts are scored whole.
    """
    if len(text) <= max(_SMALL_TEXT, 4 * len(quote)):
        return [(0, len(text))]
    words = sorted(set(_WORD.findall(quote)), key=len, reverse=True)
    candidates = [w for w in words if len(w) >= 4][:12] or [w for w in words if len(w) >= 2][:12]
    scored = sorted((text.count(w), -len(w), w) for w in candidates)
    anchors = [w for count, _, w in scored if count > 0][:3]
    margin = len(quote) + 40
    spans: list[tuple[int, int]] = []
    for word in anchors:
        pos = text.find(word)
        hits = 0
        while pos != -1 and hits < _MAX_ANCHOR_HITS:
            spans.append((max(0, pos - margin), min(len(text), pos + len(word) + margin)))
            pos = text.find(word, pos + 1)
            hits += 1
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _segment_in_text(segment: str, text: str, threshold: int) -> bool:
    if segment in text:
        return True
    if len(segment) < _MIN_FUZZY_LEN:
        return False
    quote_numbers = _numbers(segment)
    quote_negations = _negations(segment)
    for start, end in _candidate_windows(segment, text):
        window = text[start:end]
        alignment = fuzz.partial_ratio_alignment(segment, window, score_cutoff=threshold)
        if alignment is None:
            continue
        a, b = _expand_to_words(window, alignment.dest_start, alignment.dest_end)
        region = window[a:b]
        # Similar wording is not enough: a changed number ("1.8%" vs "2%") or a dropped /
        # added negation is exactly the hallucination this check exists to catch.
        if _numbers(region) == quote_numbers and _negations(region) == quote_negations:
            return True
    return False


def quote_in_text(quote: str, text: str, *, threshold: int = 90) -> bool:
    """True if ``quote`` genuinely occurs in ``text`` (the evidence quote check, C4).

    Both sides are normalised with :func:`normalize_for_match`. An exact substring passes.
    Quotes shorter than 12 characters must match exactly. Longer quotes may match fuzzily
    (rapidfuzz ``partial_ratio`` >= ``threshold``) to tolerate extraction artefacts, but the
    matched region must contain exactly the same numbers and negations as the quote.
    A quote elided with "..." passes only when every part passes.
    """
    q = normalize_for_match(quote)
    if not q:
        return False
    t = _normalized_text(text)
    if q in t:
        return True
    if len(q) < _MIN_FUZZY_LEN:
        return False
    segments = [part.strip() for part in q.split("...") if part.strip()]
    if len(segments) > 1:
        return all(_segment_in_text(part, t, threshold) for part in segments)
    return _segment_in_text(q, t, threshold)


# --------------------------------------------------------------------------- excerpts


def window_around(text: str, terms: list[str], *, radius: int = 600, max_chars: int = 6000) -> str:
    """Excerpt ``text`` around case-insensitive matches of ``terms``.

    Windows of +/- ``radius`` characters are merged when they overlap and joined with
    ``"\\n…\\n"``; the result never exceeds ``max_chars``. When no term matches, the head of
    the text is returned instead so the caller still gets context.
    """
    if max_chars <= 0:
        return ""
    cleaned = sorted({t.strip() for t in terms if t and t.strip()}, key=len, reverse=True)
    spans: list[tuple[int, int]] = []
    if cleaned:
        pattern = re.compile("|".join(re.escape(t) for t in cleaned), re.IGNORECASE)
        for m in pattern.finditer(text):
            spans.append((max(0, m.start() - radius), min(len(text), m.end() + radius)))
    if not spans:
        return truncate(text, max_chars)

    merged: list[tuple[int, int]] = []
    for start, end in spans:  # finditer yields in document order
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    sep = "\n…\n"
    pieces: list[str] = []
    used = 0
    for start, end in merged:
        piece = _trim_to_words(text, start, end)
        cost = len(piece) + (len(sep) if pieces else 0)
        if used + cost > max_chars:
            room = max_chars - used - (len(sep) if pieces else 0)
            if room > 40 or not pieces:
                pieces.append(truncate(piece, room))
            break
        pieces.append(piece)
        used += cost
    return sep.join(p for p in pieces if p)


def _trim_to_words(text: str, start: int, end: int) -> str:
    """Avoid cutting words in half at window edges (only looks a few characters around)."""
    if start > 0 and not text[start - 1].isspace():
        nxt = text.find(" ", start, min(end, start + 30))
        if nxt != -1:
            start = nxt + 1
    if end < len(text) and not text[end].isspace():
        prev = text.rfind(" ", max(start, end - 30), end)
        if prev != -1:
            end = prev
    return text[start:end].strip()
