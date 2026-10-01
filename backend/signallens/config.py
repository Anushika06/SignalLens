"""Runtime configuration.

All settings come from environment variables (prefix ``SL_``) or ``backend/.env``.
Provider API keys also accept their conventional names (``NVIDIA_API_KEY``, ``TAVILY_API_KEY``,
``EXA_API_KEY``, ``SERPER_API_KEY``; the dormant ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY`` and
``GEMINI_API_KEY`` providers can still be selected explicitly with ``SL_LLM_PROVIDER``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="SL_", extra="ignore", populate_by_name=True
    )

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://signallens:signallens@127.0.0.1:5432/signallens"
    secret_key: str = "dev-insecure-secret-change-me-before-any-deployment"

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, v: str) -> str:
        return normalize_database_url(v)

    session_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Public URLs, used for SSO redirects, email links and the agent manifest.
    public_app_url: str = "http://localhost:3000"  # the web app (frontend)
    public_api_url: str = "http://127.0.0.1:8000"  # this API

    # --- Models -------------------------------------------------------------------------
    # "auto" uses NVIDIA NIM (the only configured provider). The other providers stay in the
    # code base and can be selected explicitly.
    llm_provider: Literal["auto", "nvidia", "anthropic", "openai", "gemini", "none"] = "auto"
    nvidia_api_key: str | None = Field(
        None, validation_alias=AliasChoices("SL_NVIDIA_API_KEY", "NVIDIA_API_KEY", "NIM_API_KEY")
    )
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_timeout_s: float = 90.0
    # Comma-separated models tried in order when the tier's model fails or stalls.
    llm_fallback_models: str = "openai/gpt-oss-20b,nvidia/nemotron-3-ultra-550b-a55b"
    # Hidden reasoning ("thinking") on NIM models that support it: off everywhere (fastest),
    # on for the reasoning tier only, or on for both tiers.
    llm_thinking: Literal["off", "reasoning", "all"] = "off"
    anthropic_api_key: str | None = Field(
        None, validation_alias=AliasChoices("SL_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    openai_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_OPENAI_API_KEY", "OPENAI_API_KEY"))
    openai_base_url: str | None = Field(
        None, validation_alias=AliasChoices("SL_OPENAI_BASE_URL", "OPENAI_BASE_URL")
    )
    gemini_api_key: str | None = Field(
        None, validation_alias=AliasChoices("SL_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    # Fast tier = extraction, triage, materiality. Reasoning tier = planning, investigation, impact.
    llm_fast_model: str | None = None
    llm_reasoning_model: str | None = None

    # --- Search -------------------------------------------------------------------------
    search_provider: Literal["auto", "tavily", "exa", "serper", "none"] = "auto"
    tavily_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_TAVILY_API_KEY", "TAVILY_API_KEY"))
    exa_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_EXA_API_KEY", "EXA_API_KEY"))
    serper_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_SERPER_API_KEY", "SERPER_API_KEY"))

    # --- Collection ---------------------------------------------------------------------
    user_agent: str = "SignalLensBot/0.1 (+https://signallens.app/bot)"
    respect_robots: bool = True
    fetch_timeout_s: float = 20.0
    fetch_max_bytes: int = 8_000_000
    min_host_interval_s: float = 1.0
    backfill_months: int = 12

    # --- Worker -------------------------------------------------------------------------
    worker_concurrency: int = 4
    scheduler_tick_s: float = 10.0
    run_worker_in_api: bool = False
    digest_hour_utc: int = 3

    # --- Agent budgets ------------------------------------------------------------------
    planner_max_steps: int = 10
    planner_max_cost_usd: float = 0.60
    investigation_max_steps: int = 10
    investigation_max_cost_usd: float = 0.50

    # --- JavaScript rendering (Playwright, opt-in) -----------------------------------------
    # Renders pages that arrive as empty JavaScript shells. Needs `uv sync --extra browser` and
    # `playwright install chromium` (the Docker image can include both: INSTALL_BROWSER=1).
    render_js: bool = False
    render_timeout_s: float = 25.0

    # --- Hosted agent endpoint (aiKart method 2) ------------------------------------------
    # Comma-separated keys accepted in the `X-API-Key` header of /api/agent/*. Empty = open
    # (rate-limited per client).
    agent_api_keys: str = ""
    agent_rate_limit_per_hour: int = 30
    brief_timeout_s: float = 240.0
    # A one-shot brief can run on this machine or be delegated to a hosted SignalLens.
    remote_agent_url: str | None = None
    remote_agent_key: str | None = None

    # --- Single sign-on (OpenID Connect: Google, Microsoft Entra, Okta, ...) ---------------
    oidc_issuer: str | None = None  # e.g. https://accounts.google.com
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_provider_name: str = "Google"
    oidc_allowed_domains: str = ""  # comma-separated; empty = any verified email

    @property
    def agent_api_key_set(self) -> set[str]:
        return {k.strip() for k in self.agent_api_keys.split(",") if k.strip()}

    @property
    def oidc_allowed_domain_set(self) -> set[str]:
        return {d.strip().lower().lstrip("@") for d in self.oidc_allowed_domains.split(",") if d.strip()}

    @property
    def sso_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    # --- Demo lab -----------------------------------------------------------------------
    sandbox_enabled: bool = True
    # Show the demo-account shortcut on the sign-in page. Default: on outside production.
    demo_login: bool | None = None

    @property
    def demo_login_enabled(self) -> bool:
        return self.demo_login if self.demo_login is not None else self.env != "prod"

    # --- Outbound email: digests and approved external shares (optional) ----------------
    # auto = Brevo if BREVO_API_KEY, else Resend if RESEND_API_KEY, else SMTP if SL_SMTP_HOST.
    email_provider: Literal["auto", "brevo", "resend", "smtp", "none"] = "auto"
    brevo_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_BREVO_API_KEY", "BREVO_API_KEY"))
    resend_api_key: str | None = Field(None, validation_alias=AliasChoices("SL_RESEND_API_KEY", "RESEND_API_KEY"))
    email_from: str | None = None  # verified sender address
    email_from_name: str = "SignalLens"
    digest_email_enabled: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


def normalize_database_url(url: str) -> str:
    """Accept the connection strings hosting providers hand out (Neon, Supabase, Render).

    They look like ``postgres://u:p@host/db?sslmode=require&channel_binding=require``; the
    async driver needs ``postgresql+asyncpg://`` and ``ssl=require``, and rejects libpq-only
    parameters such as ``channel_binding``.
    """
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break
    if not url.startswith("postgresql+asyncpg://"):
        return url
    parts = urlsplit(url)
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            if value in ("require", "verify-ca", "verify-full", "prefer"):
                params.append(("ssl", "require" if value == "prefer" else value))
        elif key not in ("channel_binding", "options", "connect_timeout"):
            params.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(params)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
