"""Small, dependency-light helpers shared across SignalLens (URLs and text)."""

from signallens.util.text import (
    mask_volatile,
    normalize_for_match,
    normalize_ws,
    quote_in_text,
    sha256_text,
    truncate,
    window_around,
)
from signallens.util.urls import (
    domain_matches,
    host_of,
    normalize_url,
    publisher_key,
    registrable_domain,
)

__all__ = [
    "domain_matches",
    "host_of",
    "mask_volatile",
    "normalize_for_match",
    "normalize_url",
    "normalize_ws",
    "publisher_key",
    "quote_in_text",
    "registrable_domain",
    "sha256_text",
    "truncate",
    "window_around",
]
