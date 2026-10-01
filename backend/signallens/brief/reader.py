"""How a brief reads web pages: directly, through Tavily Extract, or direct-with-fallback.

aiKart's "Try Me Now" sandbox only lets a container reach allowlisted domains, so a
company's own website is usually unreachable from inside it. ``SL_BRIEF_READER`` picks the
strategy (read from the environment here so the brief needs no settings changes):

* ``direct`` - the normal SSRF-safe, robots-respecting :class:`~signallens.fetch.http.Fetcher`.
* ``tavily`` - Tavily's Extract API fetches pages for us; the container only needs
  ``api.tavily.com``.
* ``auto`` (default) - direct first; pages that fail with a network/DNS error, a bot wall or
  an empty JavaScript shell are retried through Tavily. When every page of a batch fails at
  the network level the reader assumes egress is restricted and goes straight to Tavily
  from then on, so a sandboxed run does not wait out a connect timeout again.

Pages disallowed by robots.txt are never re-fetched through Tavily: that would sidestep
the site owner's choice.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from signallens.fetch.extract import assess_quality, extract_result, extract_text
from signallens.search.base import SearchError

log = logging.getLogger(__name__)

ReaderMode = Literal["direct", "tavily", "auto"]


@dataclass
class ReadPage:
    url: str
    final_url: str
    title: str | None
    text: str
    ok: bool
    reason: str | None  # why the page is unusable (None when ok)
    via: str  # "direct" | "tavily"
    words: int = 0
    network_error: bool = False  # the failure looked like blocked egress / DNS / timeout
    robots_blocked: bool = False


def reader_mode() -> ReaderMode:
    mode = (os.environ.get("SL_BRIEF_READER") or "auto").strip().lower()
    return mode if mode in ("direct", "tavily", "auto") else "auto"  # type: ignore[return-value]


class PageReader(ABC):
    name: str = "reader"

    @abstractmethod
    async def read_many(self, urls: list[str]) -> list[ReadPage]:
        """Read ``urls``; one :class:`ReadPage` per URL in the same order. Never raises."""


class DirectReader(PageReader):
    name = "direct"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    async def read(self, url: str) -> ReadPage:
        fr = await self.fetcher.fetch(url)
        if fr.blocked == "robots":
            return ReadPage(url, fr.final_url or url, None, "", False, "disallowed by robots.txt", self.name,
                            robots_blocked=True)
        doc = extract_result(fr, mode="page")
        ok = doc.quality == "ok"
        return ReadPage(
            url=url, final_url=fr.final_url or url, title=doc.title, text=doc.text if ok else "",
            ok=ok, reason=None if ok else doc.quality_reason, via=self.name, words=doc.word_count,
            network_error=bool(fr.error) and fr.status is None,
        )

    async def read_many(self, urls: list[str]) -> list[ReadPage]:
        return list(await asyncio.gather(*(self.read(u) for u in urls)))


_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS = re.compile(r"(\*\*|__|`)")
_MD_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s*|(?<=\s)#{2,6}\s+")
_MD_TABLE_RULE = re.compile(r"(?m)^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def clean_markdown(text: str) -> str:
    """Tavily returns markdown-ish text; strip the markup so quotes match what a reader sees."""
    text = _MD_IMAGE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_EMPHASIS.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_TABLE_RULE.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


class TavilyReader(PageReader):
    name = "tavily"

    def __init__(self, tavily):
        self.tavily = tavily

    async def read_many(self, urls: list[str]) -> list[ReadPage]:
        if not urls:
            return []
        try:
            extracted = await self.tavily.extract(urls)
        except SearchError as e:
            return [ReadPage(u, u, None, "", False, f"Tavily extract failed: {e}", self.name) for u in urls]
        out = []
        for u, item in zip(urls, extracted, strict=False):
            if not item.ok:
                out.append(ReadPage(u, u, None, "", False, item.error or "no content", self.name))
                continue
            text = clean_markdown(item.content)
            doc = extract_text(text)
            quality, reason = assess_quality(doc, http_status=None)
            ok = quality == "ok"
            out.append(ReadPage(u, item.url or u, None, text if ok else "", ok, reason, self.name, words=doc.word_count))
        return out


class AutoReader(PageReader):
    name = "auto"

    def __init__(self, direct: DirectReader, tavily: TavilyReader | None):
        self.direct = direct
        self.tavily = tavily
        self.egress_restricted = False

    async def read_many(self, urls: list[str]) -> list[ReadPage]:
        if self.egress_restricted and self.tavily is not None:
            return await self.tavily.read_many(urls)
        pages = await self.direct.read_many(urls)
        if self.tavily is None:
            return pages
        if pages and all(p.network_error for p in pages):  # one slow site is not a sandbox
            self.egress_restricted = True
            log.info("direct fetch hit network errors; reading through Tavily Extract from now on")
        retry = [i for i, p in enumerate(pages) if not p.ok and not p.robots_blocked]
        if retry:
            again = await self.tavily.read_many([urls[i] for i in retry])
            for i, page in zip(retry, again, strict=False):
                if page.ok:
                    pages[i] = page
                else:
                    pages[i].reason = f"{pages[i].reason}; via Tavily: {page.reason}"
        return pages


def make_reader(mode: ReaderMode, *, fetcher, tavily) -> PageReader:
    """Build the reader for ``mode``; degrades to direct reading when Tavily is unavailable."""
    tav = TavilyReader(tavily) if tavily is not None and hasattr(tavily, "extract") else None
    if mode == "tavily" and tav is not None:
        return tav
    direct = DirectReader(fetcher)
    if mode == "direct" or tav is None:
        return direct
    return AutoReader(direct, tav)
