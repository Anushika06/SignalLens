"""Fetching and extraction: SSRF-safe, robots-aware HTTP, content extraction, web archive.

Usage::

    from signallens.fetch import Fetcher, extract_result

    async with Fetcher(user_agent="SignalLensBot/0.1 (+https://signallens.ai/bot)") as fetcher:
        result = await fetcher.fetch("https://razorpay.com/pricing/")
        doc = extract_result(result)          # blocks, content_hash, quality gate
"""

from signallens.fetch.extract import (
    Block,
    ExtractedDoc,
    assess_quality,
    detect_challenge,
    extract_article,
    extract_page,
    extract_pdf,
    extract_result,
    extract_text,
)
from signallens.fetch.http import Fetcher, FetchResult, decode_body
from signallens.fetch.robots import RobotsPolicy
from signallens.fetch.ssrf import SSRFBlocked, assert_public_url, is_public_ip
from signallens.fetch.wayback import ArchiveCapture, WaybackClient, WaybackError

__all__ = [
    "ArchiveCapture",
    "Block",
    "ExtractedDoc",
    "FetchResult",
    "Fetcher",
    "RobotsPolicy",
    "SSRFBlocked",
    "WaybackClient",
    "WaybackError",
    "assert_public_url",
    "assess_quality",
    "decode_body",
    "detect_challenge",
    "extract_article",
    "extract_page",
    "extract_pdf",
    "extract_result",
    "extract_text",
    "is_public_ip",
]
