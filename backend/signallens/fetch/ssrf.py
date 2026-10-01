"""SSRF guard: every URL the agent fetches must point at the public internet (C12).

An autonomous agent opens URLs it found on the web or was told about by a model. Without a
guard, a page (or a prompt injection) could make it request ``http://169.254.169.254/``
(cloud metadata credentials), ``http://localhost:5432`` or anything else on the internal
network. :func:`assert_public_url` therefore requires:

* scheme ``http`` or ``https`` and no credentials in the URL;
* a host that is not ``localhost`` / ``*.localhost`` / ``*.local`` / ``*.internal``;
* every address the host resolves to is public - not private, loopback, link-local,
  multicast, reserved, unspecified, CGNAT (100.64.0.0/10), IPv6 unique-local, or an
  IPv4-mapped / NAT64 / 6to4 wrapper around one of those. Legacy numeric forms such as
  ``http://2130706433/`` or ``http://127.1/`` are decoded and checked too.

The fetcher calls it for the first URL and again for every redirect hop.

Residual risk - DNS rebinding: the name is resolved here and again by the HTTP client when
it connects, so a hostile DNS server with a zero TTL could answer with a public address to
this check and a private one to the connection. Closing that gap needs the check at connect
time. The production mitigation is to send all agent egress through a forward proxy that
enforces the same policy on the address it actually connects to (e.g. Smokescreen), and/or a
network policy that denies the worker access to private ranges and the metadata endpoint.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

__all__ = ["SSRFBlocked", "assert_public_url", "is_public_ip"]

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal")

_EXTRA_BLOCKED = (
    ipaddress.ip_network("0.0.0.0/8"),  # "this network"
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
    ipaddress.ip_network("255.255.255.255/32"),  # broadcast
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("fec0::/10"),  # deprecated site-local
)
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


class SSRFBlocked(Exception):
    """The URL is not allowed to be fetched; the message says why (short, user-safe)."""


def _is_public(addr: IPAddress) -> bool:
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:  # ::ffff:10.0.0.1
            return _is_public(addr.ipv4_mapped)
        if addr.sixtofour is not None and not _is_public(addr.sixtofour):  # 2002:0a00:0001::
            return False
        if addr.teredo is not None and not _is_public(addr.teredo[1]):
            return False
        if any(addr in net for net in _NAT64):  # 64:ff9b::10.0.0.1 reaches 10.0.0.1 via NAT64
            return _is_public(ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF))
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return False
    if any(addr.version == net.version and addr in net for net in _EXTRA_BLOCKED):
        return False
    return addr.is_global


def is_public_ip(ip: str) -> bool:
    """True only for globally routable unicast addresses (see module docstring)."""
    candidate = ip.strip().strip("[]").split("%", 1)[0]  # drop IPv6 zone ids ("fe80::1%eth0")
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return _is_public(addr)


def _literal_ip(host: str) -> IPAddress | None:
    """Parse IP literals, including legacy IPv4 forms (``127.1``, ``0x7f000001``, ``2130706433``)."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if host and all(c in "0123456789abcdefx." for c in host) and any(c.isdigit() for c in host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


async def assert_public_url(url: str, *, allow_private: bool = False) -> None:
    """Raise :class:`SSRFBlocked` unless ``url`` may be fetched.

    ``allow_private`` (development / tests only) skips the host and address checks but
    still enforces the scheme and the no-credentials rule. DNS resolution failures are not
    policy decisions: they propagate as :class:`OSError` (``socket.gaierror``) so callers can
    report them as network errors.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise SSRFBlocked(f"malformed URL: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlocked(f"scheme {scheme or '(none)'!r} is not allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise SSRFBlocked("credentials in URLs are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise SSRFBlocked("URL has no host")
    if allow_private:
        return
    if host == "localhost" or host.endswith(_INTERNAL_SUFFIXES):
        raise SSRFBlocked(f"host {host!r} is internal")

    literal = _literal_ip(host)
    if literal is not None:
        if not _is_public(literal):
            raise SSRFBlocked(f"address {literal} is not public")
        return

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port or _DEFAULT_PORTS[scheme], type=socket.SOCK_STREAM)
    addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses:
        raise OSError(f"{host} did not resolve to any address")
    blocked = [a for a in addresses if not is_public_ip(a)]
    if blocked:
        raise SSRFBlocked(f"host {host!r} resolves to non-public address {blocked[0]}")
