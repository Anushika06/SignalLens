"""URL helpers: canonical link forms and publisher identity.

Two different questions are answered here:

* :func:`normalize_url` - "are these two links the same document?" Used to deduplicate
  search results and key snapshots. Fragments, default ports and tracking parameters never
  change the document, so they are removed; everything else is kept.
* :func:`registrable_domain` / :func:`publisher_key` - "are these two documents from the same
  publisher?" Used for evidence independence (C4): ``economictimes.indiatimes.com`` and
  ``timesofindia.indiatimes.com`` are one publisher, while two ``*.github.io`` sites are not
  (PSL private suffixes are honoured).

The Public Suffix List is tldextract's bundled snapshot. It is never fetched at runtime and
nothing is cached to disk, so these helpers are pure, fast and safe to call anywhere.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import unquote_plus, urlsplit, urlunsplit

import tldextract

__all__ = ["domain_matches", "host_of", "normalize_url", "publisher_key", "registrable_domain"]

# suffix_list_urls=() -> never download the PSL; cache_dir=None -> never write to disk.
_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)

# Click/campaign identifiers: they identify the visitor or campaign, never the document.
# fmt: off
_TRACKING_PARAMS = frozenset(
    {
        "gclid", "fbclid", "mc_cid", "mc_eid", "ref_src", "igshid",
        # other unambiguous ad-click / email-campaign identifiers
        "msclkid", "dclid", "gbraid", "wbraid", "yclid", "twclid", "_hsenc", "_hsmi", "mkt_tok",
    }
)
# fmt: on
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for equality checks and deduplication.

    Lowercases scheme and host, drops the fragment, default ports and tracking parameters
    (``utm_*``, ``gclid``, ``fbclid``...), sorts the remaining query parameters by name
    (stable, so repeated parameters keep their order) and turns an empty path into ``/``.
    Parameter encoding is preserved byte-for-byte so the result is still fetchable.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    scheme = parts.scheme.lower()
    netloc = _normalize_netloc(parts, scheme)
    path = parts.path or ("/" if netloc else "")
    return urlunsplit((scheme, netloc, path, _clean_query(parts.query), ""))


def host_of(url: str) -> str:
    """Return the lowercased host of ``url`` without port or trailing dot.

    Accepts full URLs, scheme-less URLs (``razorpay.com/pricing``) and bare hosts; returns
    ``""`` when no host can be found.
    """
    s = url.strip()
    if not s:
        return ""
    try:
        parts = urlsplit(s if ("://" in s or s.startswith("//")) else "//" + s)
        host = parts.hostname or ""
    except ValueError:
        return ""
    return host.rstrip(".").lower()


def registrable_domain(url_or_host: str) -> str:
    """Return the registrable domain ("eTLD+1") of a URL or host.

    ``https://economictimes.indiatimes.com/x`` -> ``indiatimes.com``;
    ``www.rbi.org.in`` -> ``rbi.org.in``. IP addresses and hosts without a public suffix
    (``localhost``) are returned unchanged.
    """
    host = host_of(url_or_host)
    if not host or _is_ip(host):
        return host
    try:
        domain = _TLD_EXTRACT(host).top_domain_under_public_suffix
    except Exception:  # defensive: malformed hosts must never break callers
        domain = ""
    return domain or host


def publisher_key(url: str) -> str:
    """Key used to decide whether two sources are independent publishers (C4)."""
    return registrable_domain(url)


def domain_matches(url: str, domains: Iterable[str]) -> bool:
    """True if ``url``'s host equals, or is a subdomain of, any of ``domains``.

    Domains may be given as ``razorpay.com``, ``https://razorpay.com`` or
    ``www.razorpay.com``; a leading ``www.`` is ignored so that all three also match
    ``razorpay.com`` and its other subdomains.
    """
    host = host_of(url)
    if not host:
        return False
    for domain in domains:
        d = host_of(domain)
        if d.startswith("www."):
            d = d[4:]
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _normalize_netloc(parts, scheme: str) -> str:
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:  # invalid port or IPv6 literal: keep what we were given
        return parts.netloc.lower()
    if host is None:
        return parts.netloc.lower()
    host = host.rstrip(".")
    if ":" in host:  # IPv6 literal needs its brackets back
        host = f"[{host}]"
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += ":" + parts.password
        userinfo += "@"
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        return f"{userinfo}{host}:{port}"
    return f"{userinfo}{host}"


def _clean_query(query: str) -> str:
    if not query:
        return ""
    kept = []
    for pair in query.split("&"):
        if not pair:
            continue
        name = unquote_plus(pair.split("=", 1)[0]).strip().lower()
        if name.startswith("utm_") or name in _TRACKING_PARAMS:
            continue
        kept.append(pair)
    kept.sort(key=lambda p: p.split("=", 1)[0])
    return "&".join(kept)
