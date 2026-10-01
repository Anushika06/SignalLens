"""Turn fetched documents into ordered text blocks plus a quality verdict.

* :func:`extract_page` is for *monitored pages* (pricing, product, leadership pages), where
  every visible token matters: "2%", "0%*" and "₹2499" often sit in their own tiny elements
  and must survive. It removes scripts, navigation, cookie banners, modals, newsletter
  boxes and footers, keeps hero/header marketing copy, and emits headings, paragraphs,
  list items, table rows (cells joined with " | ") and loose text in document order.
* :func:`extract_article` is for news/articles: trafilatura's main-content extraction,
  falling back to :func:`extract_page`.
* :func:`extract_pdf` reads PDFs (regulator circulars, filings) with pypdf.
* :func:`assess_quality` is the snapshot quality gate (C6): bot challenges, error pages
  and near-empty shells are marked ``blocked`` / ``degenerate`` so they are never diffed
  against a good snapshot (that would read as "everything was removed").

``content_hash`` is computed over *masked* block text, so two snapshots that differ only in
timestamps or copyright years hash identically (materiality tier 0, C7).
"""

from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin

import trafilatura
from dateutil import parser as date_parser
from lxml import etree
from lxml import html as lxml_html
from pypdf import PdfReader

from signallens.fetch.http import FetchResult
from signallens.util.text import mask_volatile, normalize_ws, sha256_text

__all__ = [
    "Block",
    "BlockKind",
    "DocKind",
    "ExtractedDoc",
    "Quality",
    "assess_quality",
    "detect_challenge",
    "extract_article",
    "extract_page",
    "extract_pdf",
    "extract_result",
    "extract_text",
]

logger = logging.getLogger(__name__)

BlockKind = Literal["heading", "paragraph", "list_item", "table_row", "other"]
Quality = Literal["ok", "degenerate", "blocked"]
DocKind = Literal["html", "pdf", "text", "xml", "json", "unknown"]


@dataclass
class Block:
    text: str
    kind: BlockKind


@dataclass
class ExtractedDoc:
    title: str | None
    text: str
    blocks: list[Block]
    content_hash: str  # sha256 of "\n".join(mask_volatile(normalize_ws(b.text)) for b in blocks)
    word_count: int
    quality: Quality
    quality_reason: str | None
    published_at: datetime | None
    canonical_url: str | None
    description: str | None
    lang: str | None
    kind: DocKind
    #: Anti-bot marker found in the *raw* markup at extraction time. Kept so that
    #: re-assessing the doc later still knows it was a challenge page.
    challenge: str | None = None


# --------------------------------------------------------------------------- quality gate

_BLOCKED_STATUSES = frozenset({401, 403, 429, 503})
_MIN_WORDS = 30
_MIN_REFERENCE_RATIO = 0.35
# Challenge pages are tiny. Markers are only trusted on small pages, so a real page that
# merely embeds reCAPTCHA in a form, or an article *about* captchas, is never "blocked".
_SMALL_PAGE_WORDS = 250
_TINY_PAGE_WORDS = 80
_CHALLENGE_TITLES = (
    "just a moment",
    "attention required! | cloudflare",
    "access denied",
    "request rejected",
    "pardon our interruption",
    "are you a robot",
    "robot or human",
    "security check",
    "ddos-guard",
    "verify you are human",
    "please verify you are a human",
)
_STRONG_MARKERS = (
    "cf-browser-verification",
    "cf-chl",
    "cf_chl",
    "enable javascript and cookies to continue",
    "request unsuccessful. incapsula",
    "_incapsula_resource",
    "incapsula incident id",
    "checking your browser before accessing",
    "attention required! | cloudflare",
    "just a moment...",
)
_WEAK_MARKERS = ("captcha", "access denied", "challenge-platform", "datadome", "perimeterx")


def detect_challenge(raw: str | None, title: str | None, word_count: int) -> str | None:
    """Return the anti-bot/challenge marker found, or ``None``.

    ``raw`` may be HTML (preferred: markers such as ``cf-chl`` live in scripts and
    attributes) or plain text; ``word_count`` is the *visible* word count.
    """
    if word_count >= _SMALL_PAGE_WORDS:
        return None
    lowered_title = (title or "").strip().casefold()
    for marker in _CHALLENGE_TITLES:
        if lowered_title.startswith(marker):
            return f"title {title.strip()!r}" if title else marker
    head = (raw or "")[:200_000].casefold()
    for marker in _STRONG_MARKERS:
        if marker in head:
            return marker
    if word_count < _TINY_PAGE_WORDS:
        for marker in _WEAK_MARKERS:
            if marker in head:
                return marker
    return None


def assess_quality(
    doc: ExtractedDoc, *, http_status: int | None, reference_word_count: int | None = None
) -> tuple[Quality, str | None]:
    """Classify a snapshot as ``ok``, ``degenerate`` or ``blocked`` (with a reason).

    * ``blocked``: HTTP 401/403/429/503, or a bot-challenge page.
    * ``degenerate``: another HTTP error status, fewer than 30 words, or fewer than 35% of
      ``reference_word_count`` (the page's usual size, e.g. the last good snapshot).
    """
    if http_status in _BLOCKED_STATUSES:
        return "blocked", f"HTTP {http_status}"
    marker = doc.challenge or detect_challenge(doc.text, doc.title, doc.word_count)
    if marker:
        return "blocked", f"anti-bot challenge page ({marker})"
    if http_status is not None and http_status >= 400:
        return "degenerate", f"HTTP {http_status} error page"
    if doc.word_count < _MIN_WORDS:
        return "degenerate", f"too little text ({doc.word_count} words)"
    if reference_word_count and doc.word_count < _MIN_REFERENCE_RATIO * reference_word_count:
        return (
            "degenerate",
            f"only {doc.word_count} words vs about {reference_word_count} usually (<35%)",
        )
    return "ok", None


# --------------------------------------------------------------------------- doc assembly

_INVISIBLE = dict.fromkeys(map(ord, "​⁠﻿­"), None)


def _clean_text(s: str) -> str:
    """Collapse whitespace (incl. NBSP) and drop invisible characters; no NFKC here so
    the text keeps its original glyphs ("™", "²") for display and quoting."""
    return " ".join(s.translate(_INVISIBLE).split())


def _content_hash(blocks: list[Block]) -> str:
    return sha256_text("\n".join(mask_volatile(normalize_ws(b.text)) for b in blocks))


def _make_doc(
    blocks: list[Block],
    *,
    kind: DocKind,
    title: str | None = None,
    published_at: datetime | None = None,
    canonical_url: str | None = None,
    description: str | None = None,
    lang: str | None = None,
    challenge: str | None = None,
) -> ExtractedDoc:
    text = "\n".join(b.text for b in blocks)
    doc = ExtractedDoc(
        title=title,
        text=text,
        blocks=blocks,
        content_hash=_content_hash(blocks),
        word_count=len(text.split()),
        quality="ok",
        quality_reason=None,
        published_at=published_at,
        canonical_url=canonical_url,
        description=description,
        lang=lang,
        kind=kind,
        challenge=challenge,
    )
    doc.quality, doc.quality_reason = assess_quality(doc, http_status=None)
    return doc


def _empty_doc(kind: DocKind, quality: Quality, reason: str) -> ExtractedDoc:
    doc = _make_doc([], kind=kind)
    doc.quality, doc.quality_reason = quality, reason
    return doc


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        parsed = date_parser.parse(value.strip())
    except (ValueError, OverflowError, TypeError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


# --------------------------------------------------------------------------- HTML cleaning

# fmt: off
_DROP_TAGS = frozenset(
    {
        "script", "style", "noscript", "svg", "iframe", "template", "head", "link", "meta", "base",
        "input", "select", "textarea", "button", "option", "optgroup", "datalist",
        "nav", "footer", "aside", "dialog",
        "object", "embed", "canvas", "audio", "video", "source", "track", "map", "picture",
    }
)
# fmt: on
_DROP_ROLES = frozenset({"navigation", "menu", "menubar", "contentinfo", "dialog", "alertdialog", "search"})
# Consent-management vendors and banners. (Deliberately not "cmp-": that prefix is used by
# every Adobe Experience Manager component, and not "truste": it matches "trusted-by".)
_CONSENT = re.compile(
    r"cookie|consent|gdpr|onetrust|cookiebot|didomi|usercentrics|trustarc|truste-|osano|termly|iubenda",
    re.IGNORECASE,
)
_ALWAYS_DROP_TOKEN = re.compile(
    r"^(?:.*breadcrumb.*|.*newsletter.*|skip(?:[-_].*)?|skiplink"
    r"|(?:site|page|global|main|layout)?[-_]?footer(?:[-_].*)?"
    r"|modal(?:[-_].*)?|popup(?:[-_].*)?|pop-up(?:[-_].*)?|subscribe(?:[-_].*)?"
    r"|(?:site|main|top|global|primary|mobile|header|sub|side|mega)?[-_]?(?:nav|navbar|navigation)(?:[-_].*)?)$"
)
# "menu" is ambiguous (a restaurant's menu is content), so it is dropped only when link-dense.
_MENU_TOKEN = re.compile(r"(?:^|[-_])(?:mega|sub|dropdown|side|main|mobile)?[-_]?menu(?:s|bar)?(?:$|[-_])")
_ARIA_DROP = re.compile(r"breadcrumb|cookie|consent|navigation|footer", re.IGNORECASE)
_LINK_DENSE = 0.5
_NAV_HEADER_DENSITY = 0.6


def _tokens(el: etree._Element) -> list[str]:
    classes = (el.get("class") or "").lower().split()
    ident = (el.get("id") or "").strip().lower()
    return [*classes, ident] if ident else classes


def _squash_len(s: str) -> int:
    return len("".join(s.split()))


def _link_density(el: etree._Element) -> float:
    total = _squash_len(el.text_content())
    if total == 0:
        return 1.0
    linked = sum(_squash_len(a.text_content()) for a in el.iter("a"))
    return min(1.0, linked / total)


_NEVER_HEURISTIC = frozenset({"html", "body", "main", "article"})
_VETO_SHARE = 0.6  # a "banner" holding most of the page's text is really a wrapper


def _looks_like_boilerplate(el: etree._Element, tag: str) -> bool:
    """Class/id/role/aria heuristics for banners, menus, modals, footers and skip links."""
    if tag in _NEVER_HEURISTIC:
        return False
    role = (el.get("role") or "").strip().lower()
    if role in _DROP_ROLES or (el.get("aria-modal") or "").lower() == "true":
        return True
    tokens = _tokens(el)
    if any(_CONSENT.search(t) or _ALWAYS_DROP_TOKEN.match(t) for t in tokens):
        return True
    aria_label = el.get("aria-label") or ""
    if aria_label and _ARIA_DROP.search(aria_label):
        return True
    if tag == "a" and _clean_text(el.text_content()).lower().startswith("skip to"):
        return True
    if any(_MENU_TOKEN.search(t) for t in tokens) or "menu" in aria_label.lower():
        return _link_density(el) >= _LINK_DENSE
    return False


def _label_icons_in_cells(root: etree._Element) -> None:
    """Keep the meaning of ✓/✗ icons in comparison tables (they are SVG/IMG, removed later)."""
    seen: set[etree._Element] = set()
    for cell in root.iter("td", "th"):
        for icon in list(cell.iter("img", "svg")):
            if icon in seen:  # nested tables: an icon is visited once
                continue
            seen.add(icon)
            label = icon.get("aria-label") or icon.get("alt") or icon.get("title")
            if not label and icon.tag == "svg":
                title = icon.find(".//title")
                label = title.text if title is not None else None
            if label and label.strip():
                icon.tail = f" {label.strip()} " + (icon.tail or "")


def _drop(el: etree._Element) -> None:
    if el.getparent() is not None:
        el.drop_tree()  # keeps the element's tail text in the parent


def _clean_tree(root: etree._Element) -> None:
    _label_icons_in_cells(root)
    body = root.find("body")
    total = _squash_len((body if body is not None else root).text_content())
    doomed: list[etree._Element] = []
    walker = etree.iterwalk(root, events=("start",))
    for _, el in walker:
        if el is root or not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if tag in _DROP_TAGS:
            doomed.append(el)
            walker.skip_subtree()
        elif _looks_like_boilerplate(el, tag):
            # Safety veto: a wrapper <div class="nav-open"> must not take the page with it.
            if total > 300 and _squash_len(el.text_content()) > _VETO_SHARE * total:
                continue
            doomed.append(el)
            walker.skip_subtree()
    for el in doomed:
        _drop(el)
    # A <header> usually holds the logo and navigation, but hero copy ("Start accepting
    # payments at just 2%") sometimes lives there too: drop it only if it is mostly links.
    for header in list(root.iter("header")):
        if header.getparent() is None:
            continue
        text_len = _squash_len(header.text_content())
        linked = sum(_squash_len(a.text_content()) for a in header.iter("a"))
        if text_len == 0 or linked / text_len >= _NAV_HEADER_DENSITY or text_len - linked < 20:
            _drop(header)


# --------------------------------------------------------------------------- block emission

_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_PARAGRAPHS = frozenset(
    {"p", "blockquote", "figcaption", "dt", "dd", "pre", "address", "caption", "summary", "legend"}
)
# fmt: off
_INLINE = frozenset(
    {
        "a", "abbr", "acronym", "b", "bdi", "bdo", "big", "cite", "code", "data", "dfn", "em", "font",
        "i", "img", "kbd", "label", "mark", "q", "rp", "rt", "ruby", "s", "samp", "small", "span",
        "strike", "strong", "sub", "sup", "time", "tt", "u", "var", "wbr", "del", "ins", "output",
        "meter", "progress", "nobr",
    }
)
# fmt: on
_ROW_MAX_CHARS = 1000
_BOUNDARY = object()  # marks an inline element edge in the text buffer
# Visual separators ("|", "•", "/") carry no content; footnote marks ("*", "†") do and are kept.
_SEPARATOR_ONLY = re.compile(r"[|•·/\\\-–—_:;,.\s]+")


def _kind_for(tag: str) -> BlockKind:
    if tag in _HEADINGS:
        return "heading"
    if tag in _PARAGRAPHS:
        return "paragraph"
    if tag == "li":
        return "list_item"
    return "other"


def _needs_space(before: str, after: str) -> bool:
    """Should adjacent inline elements with no whitespace between them get a space?

    Browsers render ``<span>2%</span><span>per transaction</span>`` as-is, but such markup
    is almost always laid out as separate words. We add a space between word-like
    characters, never inside numbers ("₹" + "2499", "2" + ".5%") or before trailing marks
    ("0%" + "*").
    """
    if before.isspace() or after.isspace():
        return False
    if before.isdigit() and after.isdigit():
        return False
    left = before.isalnum() or before in "%)]!?.,;:"
    right = after.isalnum() or after in "([" or unicodedata.category(after) == "Sc"
    if before in ".," and after.isdigit():
        return False
    return left and right


def _join_inline(pieces: list[object]) -> str:
    out: list[str] = []
    pending = False
    for piece in pieces:
        if piece is _BOUNDARY:
            pending = True
            continue
        assert isinstance(piece, str)
        if not piece:
            continue
        if pending and out and out[-1] and _needs_space(out[-1][-1], piece[0]):
            out.append(" ")
        pending = False
        out.append(piece)
    return _clean_text("".join(out))


def _inline_text(el: etree._Element) -> str:
    """All text under ``el`` joined as one line (used for table cells)."""
    pieces: list[object] = []
    walker = etree.iterwalk(el, events=("start", "end"))
    for event, node in walker:
        if not isinstance(node.tag, str):
            continue
        tag = node.tag.lower()
        if event == "start":
            pieces.append(_BOUNDARY if tag in _INLINE else " ")
            if node.text:
                pieces.append(node.text)
        else:
            pieces.append(_BOUNDARY if tag in _INLINE else " ")
            if node is not el and node.tail:
                pieces.append(node.tail)
    return _join_inline(pieces)


def _row_text(tr: etree._Element) -> str | None:
    """``"cell | cell"`` for simple data rows; ``None`` for layout rows (nested tables, huge cells)."""
    cells = [c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ("td", "th")]
    if not cells or tr.find(".//table") is not None:
        return None
    if _squash_len(tr.text_content()) > _ROW_MAX_CHARS:
        return None
    texts = [t for t in (_inline_text(c) for c in cells) if t]
    return " | ".join(texts)


class _BlockBuilder:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.pieces: list[object] = []

    def add_text(self, text: str | None) -> None:
        if text:
            self.pieces.append(text)

    def boundary(self) -> None:
        self.pieces.append(_BOUNDARY)

    def flush(self, kind: BlockKind) -> None:
        text = _join_inline(self.pieces)
        self.pieces = []
        self.add_block(text, kind)

    def add_block(self, text: str, kind: BlockKind) -> None:
        if not text or _SEPARATOR_ONLY.fullmatch(text):
            return
        if not (self.blocks and self.blocks[-1].text == text):
            self.blocks.append(Block(text, kind))


def _emit_blocks(root: etree._Element) -> list[Block]:
    builder = _BlockBuilder()
    kinds: list[BlockKind | None] = ["other"]  # None marks a table row emitted as one block
    walker = etree.iterwalk(root, events=("start", "end"))
    for event, el in walker:
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if event == "start":
            if tag == "tr":
                row = _row_text(el)
                if row is not None:
                    builder.flush(kinds[-1] or "other")
                    builder.add_block(row, "table_row")
                    kinds.append(None)
                    walker.skip_subtree()
                    continue
            if tag == "br":
                builder.add_text(" ")
            elif tag in _INLINE:
                builder.boundary()
            else:
                builder.flush(kinds[-1] or "other")
                kinds.append(_kind_for(tag))
            builder.add_text(el.text)
        else:
            if tag in _INLINE:
                builder.boundary()
            elif tag != "br":
                kind = kinds.pop()
                if kind is not None:
                    builder.flush(kind)
            builder.add_text(el.tail)  # a tail belongs to the parent's block
    builder.flush(kinds[-1] or "other")
    return builder.blocks


# --------------------------------------------------------------------------- HTML entry points

_DATE_META_KEYS = (
    "article:published_time",
    "og:published_time",
    "og:article:published_time",
    "datepublished",
    "parsely-pub-date",
    "pubdate",
    "publishdate",
    "publish-date",
    "date",
    "dc.date",
    "dc.date.issued",
)


@dataclass
class _HtmlMeta:
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    lang: str | None = None
    published_at: datetime | None = None


def _parse_html(html: str) -> etree._Element | None:
    parser = lxml_html.HTMLParser(encoding="utf-8", remove_comments=True, remove_pis=True, no_network=True)
    try:
        return lxml_html.document_fromstring(html.encode("utf-8", errors="replace"), parser=parser)
    except (etree.ParserError, ValueError):
        return None


def _read_meta(root: etree._Element, url: str | None) -> _HtmlMeta:
    meta = _HtmlMeta()
    titles = root.xpath("//head/title") or root.xpath("//title[not(ancestor::svg)]")
    if titles:
        meta.title = _clean_text(titles[0].text_content()) or None
    values: dict[str, str] = {}
    for tag in root.iter("meta"):
        key = (tag.get("property") or tag.get("name") or tag.get("itemprop") or "").strip().lower()
        content = (tag.get("content") or "").strip()
        if key and content and key not in values:
            values[key] = content
    meta.title = meta.title or values.get("og:title") or values.get("twitter:title")
    meta.description = values.get("description") or values.get("og:description")
    for link in root.iter("link"):
        rels = (link.get("rel") or "").lower().split()
        href = (link.get("href") or "").strip()
        if "canonical" in rels and href:
            meta.canonical_url = urljoin(url, href) if url else href
            break
    lang = root.get("lang") or root.get("xml:lang")
    meta.lang = lang.strip() if lang and lang.strip() else None
    for key in _DATE_META_KEYS:
        meta.published_at = _parse_date(values.get(key))
        if meta.published_at:
            break
    return meta


def extract_page(html: str, url: str | None = None) -> ExtractedDoc:
    """Extract every visible, non-boilerplate text block of a monitored page (see module doc)."""
    root = _parse_html(html)
    if root is None:
        return _empty_doc("html", "degenerate", "empty or unparseable HTML")
    meta = _read_meta(root, url)
    _clean_tree(root)
    blocks = _emit_blocks(root)
    word_count = sum(len(b.text.split()) for b in blocks)
    return _make_doc(
        blocks,
        kind="html",
        title=meta.title,
        published_at=meta.published_at,
        canonical_url=meta.canonical_url,
        description=meta.description,
        lang=meta.lang,
        challenge=detect_challenge(html, meta.title, word_count),
    )


def _trafilatura(html: str, url: str | None) -> dict[str, object] | None:
    try:
        document = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_comments=False)
    except Exception as exc:  # trafilatura is robust, but a parser crash must not stop a run
        logger.debug("trafilatura failed for %s: %s", url, exc)
        return None
    if document is None:
        return None
    if isinstance(document, dict):
        return document
    as_dict = getattr(document, "as_dict", None)
    return as_dict() if callable(as_dict) else None


def extract_article(html: str, url: str | None = None) -> ExtractedDoc:
    """Main-content extraction for news and articles (trafilatura), with page fallback.

    Blocks are the article's paragraphs. The precise ``article:published_time`` meta tag
    wins over trafilatura's date guess (which is day-precision only).
    """
    page = extract_page(html, url)
    result = _trafilatura(html, url)
    text = str(result.get("text") or "") if result else ""
    blocks = [Block(line, "paragraph") for line in (_clean_text(raw) for raw in text.split("\n")) if line]
    words = sum(len(b.text.split()) for b in blocks)
    if not blocks or (words < _MIN_WORDS and page.word_count >= words):
        return page
    assert result is not None
    return _make_doc(
        blocks,
        kind="html",
        title=str(result.get("title") or "") or page.title,
        published_at=page.published_at or _parse_date(str(result.get("date") or "")),
        canonical_url=page.canonical_url or (str(result.get("url") or "") or None),
        description=page.description or (str(result.get("description") or "") or None),
        lang=page.lang or (str(result.get("language") or "") or None),
        challenge=page.challenge,
    )


# --------------------------------------------------------------------------- PDF / text / JSON

_LONG_PARAGRAPH = 1500


def _paragraph_blocks(text: str) -> list[Block]:
    """Blank-line separated paragraphs; oversized ones (no blank lines at all) split by line."""
    blocks: list[Block] = []
    for para in re.split(r"\n\s*\n", text):
        lines = [_clean_text(line) for line in para.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        joined = " ".join(lines)
        if len(joined) > _LONG_PARAGRAPH and len(lines) > 1:
            blocks.extend(Block(line, "paragraph") for line in lines)
        else:
            blocks.append(Block(joined, "paragraph"))
    return blocks


def extract_pdf(data: bytes) -> ExtractedDoc:
    """Extract text from a PDF; title from metadata or the first line. Never raises."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            return _empty_doc("pdf", "degenerate", "encrypted PDF")
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # one broken page should not lose the rest
                logger.debug("pdf page extraction failed: %s", exc)
        info = reader.metadata
    except Exception as exc:
        return _empty_doc("pdf", "degenerate", f"unreadable PDF: {type(exc).__name__}")
    blocks = _paragraph_blocks("\n\n".join(pages))
    title: str | None = None
    published_at: datetime | None = None
    if info is not None:
        try:
            title = _clean_text(info.title or "") or None
            created = info.creation_date
            if created is not None:
                published_at = (
                    created.replace(tzinfo=UTC) if created.tzinfo is None else created.astimezone(UTC)
                )
        except Exception:  # malformed metadata dates are common
            pass
    if not title and blocks:
        title = blocks[0].text[:200]
    return _make_doc(blocks, kind="pdf", title=title, published_at=published_at)


def extract_text(text: str, *, kind: DocKind = "text") -> ExtractedDoc:
    """Plain text split into paragraphs."""
    return _make_doc(_paragraph_blocks(text), kind=kind)


def _extract_json(text: str) -> ExtractedDoc:
    try:
        data = json.loads(text)
    except ValueError:
        return extract_text(text, kind="json")
    pretty = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)
    blocks = [Block(line.strip(), "other") for line in pretty.splitlines() if line.strip()]
    return _make_doc(blocks, kind="json")


# --------------------------------------------------------------------------- dispatcher

_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_XML_TYPES = frozenset({"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"})
_JSON_TYPES = frozenset({"application/json", "application/ld+json"})


def extract_result(
    result: FetchResult,
    *,
    mode: Literal["page", "article"] = "page",
    reference_word_count: int | None = None,
) -> ExtractedDoc:
    """Extract whatever a :class:`FetchResult` holds and run the quality gate on it.

    Blocked fetches give a ``blocked`` doc; network errors and 304s (no body) give a
    ``degenerate`` one. Never raises.
    """
    if result.blocked:
        return _empty_doc("unknown", "blocked", f"fetch blocked ({result.blocked})")
    if result.error:
        return _empty_doc("unknown", "degenerate", f"fetch failed: {result.error}")
    if result.not_modified:
        return _empty_doc("unknown", "degenerate", "not modified (304): no body to extract")

    media = result.media_type
    text = result.text
    try:
        if media == "application/pdf" or result.content[:5] == b"%PDF-":
            doc = extract_pdf(result.content)
        elif text is None:
            doc = _empty_doc("unknown", "degenerate", f"unsupported content type {media or 'unknown'!r}")
        elif media in _HTML_TYPES or (not media and re.search(r"<html|<!doctype html", text[:2048], re.I)):
            url = result.final_url or result.url
            doc = extract_article(text, url) if mode == "article" else extract_page(text, url)
        elif media in _XML_TYPES or media.endswith("+xml"):
            doc = extract_page(text, result.final_url or result.url)
            doc.kind = "xml"
        elif media in _JSON_TYPES or media.endswith("+json"):
            doc = _extract_json(text)
        else:
            doc = extract_text(text)
    except Exception as exc:  # extraction bugs must degrade the snapshot, not crash the run
        logger.exception("extraction failed for %s", result.url)
        return _empty_doc("unknown", "degenerate", f"extraction failed: {type(exc).__name__}")

    quality, reason = assess_quality(
        doc, http_status=result.status, reference_word_count=reference_word_count
    )
    if not doc.blocks and doc.quality_reason and quality == "degenerate" and (result.status or 0) < 400:
        reason = doc.quality_reason  # keep the specific cause ("encrypted PDF", "unparseable HTML")
    doc.quality, doc.quality_reason = quality, reason
    return doc
