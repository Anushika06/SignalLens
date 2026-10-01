"""Shared fixtures for unit tests. Unit tests never touch the network."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def fixture_text() -> Callable[[str], str]:
    """Read a text fixture from tests/fixtures by file name."""

    def read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return read


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Make retry backoff instant; returns the list of delays that would have been slept."""
    import signallens.fetch.wayback as wayback
    import signallens.llm.base as llm_base
    import signallens.search.base as search_base

    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    for module in (llm_base, search_base, wayback):
        monkeypatch.setattr(module, "_sleep", fake_sleep)
    return delays


@dataclass
class FakeDNS:
    """``records`` maps host -> addresses (empty list = NXDOMAIN); others resolve to PUBLIC_IP."""

    records: dict[str, list[str]] = field(default_factory=dict)
    lookups: list[str] = field(default_factory=list)


@pytest.fixture
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> FakeDNS:
    """Replace the event loop's ``getaddrinfo`` so SSRF checks never hit real DNS."""
    dns = FakeDNS()

    async def fake_getaddrinfo(self, host, port, *args, **kwargs):
        dns.lookups.append(host)
        addresses = dns.records.get(host, [PUBLIC_IP])
        if not addresses:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        out = []
        for ip in addresses:
            if ":" in ip:
                out.append(
                    (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0, 0, 0))
                )
            else:
                out.append((socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0)))
        return out

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
    return dns
