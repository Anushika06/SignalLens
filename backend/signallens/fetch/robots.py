"""robots.txt policy with RFC 9309 semantics (responsible collection, C12).

* robots.txt answers 4xx (or any non-2xx, non-5xx status) -> no rules: everything allowed.
* 5xx or a network error -> the site is treated as fully disallowed until the cache entry
  expires ("when in doubt, stay out").
* 2xx -> parsed with :class:`urllib.robotparser.RobotFileParser`, then its rules are
  upgraded to RFC 9309 matching: ``*`` / ``$`` wildcards and "longest match wins" (``Allow``
  wins ties). The stdlib alone uses first-match-in-file-order and treats wildcards
  literally, which wrongly blocks e.g. ``Disallow: /`` + ``Allow: /pricing``.

Groups are matched on the product token of our user agent (``SignalLensBot`` from
``SignalLensBot/0.1 (+https://...)``). Results are cached per origin (scheme + host + port)
for ``ttl_s`` seconds and at most one robots.txt fetch per origin is in flight at a time.
``Crawl-delay`` is exposed so the fetcher can space its requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

__all__ = ["RobotsPolicy"]

logger = logging.getLogger(__name__)

FetchText = Callable[[str], Awaitable[tuple[int | None, str | None]]]


class _Rule:
    """RFC 9309 rule: ``*`` matches any run of characters, a trailing ``$`` anchors the end.

    Works on the percent-quoted paths that :class:`RobotFileParser` stores and compares.
    """

    def __init__(self, path: str, allowance: bool) -> None:
        self.path = path
        self.allowance = allowance
        anchored = path.endswith("%24")
        body = path[:-3] if anchored else path
        pattern = ".*".join(re.escape(part) for part in body.split("%2A"))
        self._regex = re.compile(pattern + ("$" if anchored else ""))
        # Specificity is the length of the rule as written (Google's reference parser):
        # '*' and '$' count as one character each, not as their %-escapes.
        self.specificity = len(unquote(path))

    def applies_to(self, filename: str) -> bool:
        return self._regex.match(filename) is not None

    def __str__(self) -> str:
        return ("Allow" if self.allowance else "Disallow") + ": " + self.path


def _upgrade_rules(parser: urllib.robotparser.RobotFileParser) -> None:
    """Replace stdlib rule lines with RFC 9309 rules, most specific first.

    ``Entry.allowance`` returns the first rule that applies, so ordering by specificity
    (longest path first, ``Allow`` before ``Disallow`` on ties) yields longest-match-wins.
    """
    entries = list(parser.entries)
    if parser.default_entry is not None:
        entries.append(parser.default_entry)
    for entry in entries:
        rules = [_Rule(line.path, line.allowance) for line in entry.rulelines]
        rules.sort(key=lambda r: (-r.specificity, not r.allowance))
        entry.rulelines = rules


def product_token(user_agent: str) -> str:
    """``"SignalLensBot/0.1 (+https://x)"`` -> ``"SignalLensBot"``."""
    match = re.match(r"[A-Za-z0-9_-]+", user_agent.strip())
    return match.group(0) if match else user_agent.strip()


@dataclass
class _CacheEntry:
    parser: urllib.robotparser.RobotFileParser
    expires_at: float


class RobotsPolicy:
    """Answers "may we fetch this URL?" and "how long must we wait between requests?"."""

    def __init__(
        self,
        fetch_text: FetchText,
        user_agent: str,
        ttl_s: float = 3600,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch_text = fetch_text
        self.user_agent = user_agent
        self.token = product_token(user_agent)
        self.ttl_s = ttl_s
        self._clock = clock
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        """True if our user agent may fetch ``url`` (malformed URLs are refused)."""
        parser = await self._parser_for(url)
        if parser is None:
            return False
        return parser.can_fetch(self.token, url)

    async def crawl_delay(self, url: str) -> float | None:
        """The ``Crawl-delay`` (seconds) that applies to us on ``url``'s site, if any."""
        parser = await self._parser_for(url)
        if parser is None or parser.disallow_all or parser.allow_all:
            return None
        delay = parser.crawl_delay(self.token)
        return float(delay) if delay is not None else None

    async def _parser_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            parts = urlsplit(url)
            origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}"
        except ValueError:
            return None
        if not parts.scheme or not parts.netloc:
            return None
        entry = self._cache.get(origin)
        if entry is not None and entry.expires_at > self._clock():
            return entry.parser
        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:  # one robots.txt fetch per origin at a time
            entry = self._cache.get(origin)
            if entry is not None and entry.expires_at > self._clock():
                return entry.parser
            parser = await self._load(origin)
            self._cache[origin] = _CacheEntry(parser, self._clock() + self.ttl_s)
            return parser

    async def _load(self, origin: str) -> urllib.robotparser.RobotFileParser:
        robots_url = f"{origin}/robots.txt"
        parser = urllib.robotparser.RobotFileParser(robots_url)
        try:
            status, text = await self._fetch_text(robots_url)
        except Exception as exc:  # the fetch callable should not raise, but never trust it
            logger.warning("robots.txt fetch for %s raised %s", origin, exc)
            status, text = None, None

        if status is None or status >= 500:
            logger.info("robots.txt for %s unreachable (status=%s): disallowing until TTL", origin, status)
            parser.disallow_all = True
        elif 200 <= status < 300:
            parser.parse((text or "").splitlines())
            _upgrade_rules(parser)
        else:  # 4xx and anything else: no usable robots.txt -> no restrictions
            parser.allow_all = True
        parser.modified()
        return parser
