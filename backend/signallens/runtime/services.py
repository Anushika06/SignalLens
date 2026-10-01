"""Shared services for pipelines and agents: database, fetcher, archive, search, models.

Built once per process from settings. Tests build it with scripted models, static search
results and sandbox pages instead of real providers.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from signallens.config import Settings
from signallens.db.models import SandboxPage
from signallens.fetch.http import Fetcher
from signallens.fetch.wayback import WaybackClient
from signallens.runtime.gateway import DEFAULT_MODELS, ModelGateway
from signallens.search.base import SearchProvider

log = logging.getLogger(__name__)


class NotConfigured(RuntimeError):
    """A capability needs an API key that is not configured."""


@dataclass
class Services:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    fetcher: Fetcher
    wayback: WaybackClient
    llm: ModelGateway | None = None
    search: SearchProvider | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def require_llm(self) -> ModelGateway:
        if self.llm is None:
            raise NotConfigured(
                "No language model is configured. Add ANTHROPIC_API_KEY, OPENAI_API_KEY or GEMINI_API_KEY "
                "to backend/.env and restart."
            )
        return self.llm

    def require_search(self) -> SearchProvider:
        if self.search is None:
            raise NotConfigured(
                "No search provider is configured. Add TAVILY_API_KEY, EXA_API_KEY or SERPER_API_KEY "
                "to backend/.env and restart."
            )
        return self.search

    async def aclose(self) -> None:
        for closer in (self.fetcher.aclose, self.wayback.aclose,
                       getattr(self.search, "aclose", None), getattr(getattr(self.llm, "provider", None), "aclose", None)):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:  # pragma: no cover - best effort on shutdown
                log.debug("close failed", exc_info=True)


def build_gateway(settings: Settings) -> ModelGateway | None:
    choice = settings.llm_provider
    candidates = ["anthropic", "openai", "gemini"] if choice == "auto" else [choice]
    for name in candidates:
        if name == "anthropic" and settings.anthropic_api_key:
            from signallens.llm.anthropic import AnthropicProvider

            provider = AnthropicProvider(settings.anthropic_api_key)
        elif name == "openai" and (settings.openai_api_key or settings.openai_base_url):
            from signallens.llm.openai import OpenAIProvider

            provider = OpenAIProvider(settings.openai_api_key or "not-needed", base_url=settings.openai_base_url)
        elif name == "gemini" and settings.gemini_api_key:
            from signallens.llm.gemini import GeminiProvider

            provider = GeminiProvider(settings.gemini_api_key)
        else:
            continue
        fast, reasoning = DEFAULT_MODELS[name]
        return ModelGateway(
            provider, provider_name=name,
            fast_model=settings.llm_fast_model or fast,
            reasoning_model=settings.llm_reasoning_model or reasoning,
        )
    return None


def build_search(settings: Settings) -> SearchProvider | None:
    choice = settings.search_provider
    candidates = ["tavily", "exa", "serper"] if choice == "auto" else [choice]
    for name in candidates:
        if name == "tavily" and settings.tavily_api_key:
            from signallens.search.tavily import TavilySearch

            return TavilySearch(settings.tavily_api_key)
        if name == "exa" and settings.exa_api_key:
            from signallens.search.exa import ExaSearch

            return ExaSearch(settings.exa_api_key)
        if name == "serper" and settings.serper_api_key:
            from signallens.search.serper import SerperSearch

            return SerperSearch(settings.serper_api_key)
    return None


def sandbox_resolver(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str], Awaitable[tuple[str, str] | None]]:
    async def resolve(slug: str) -> tuple[str, str] | None:
        async with session_factory() as s:
            page = await s.get(SandboxPage, slug.strip("/"))
            return (page.html, page.title) if page else None

    return resolve


def build_services(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    llm: ModelGateway | None = None,
    search: SearchProvider | None = None,
    fetcher: Fetcher | None = None,
    wayback: WaybackClient | None = None,
    use_real_providers: bool = True,
) -> Services:
    fetcher = fetcher or Fetcher(
        user_agent=settings.user_agent,
        timeout_s=settings.fetch_timeout_s,
        max_bytes=settings.fetch_max_bytes,
        respect_robots=settings.respect_robots,
        min_host_interval_s=settings.min_host_interval_s,
        sandbox_resolver=sandbox_resolver(session_factory) if settings.sandbox_enabled else None,
    )
    return Services(
        settings=settings,
        session_factory=session_factory,
        fetcher=fetcher,
        wayback=wayback or WaybackClient(fetcher),
        llm=llm if llm is not None else (build_gateway(settings) if use_real_providers else None),
        search=search if search is not None else (build_search(settings) if use_real_providers else None),
    )
