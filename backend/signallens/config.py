"""Runtime configuration.

All settings come from environment variables (prefix ``SL_``) or ``backend/.env``.
Provider API keys also accept their conventional names (``ANTHROPIC_API_KEY``,
``OPENAI_API_KEY``, ``GEMINI_API_KEY``/``GOOGLE_API_KEY``, ``TAVILY_API_KEY``,
``EXA_API_KEY``, ``SERPER_API_KEY``) so existing shells work unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="SL_", extra="ignore", populate_by_name=True
    )

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://signallens:signallens@127.0.0.1:5432/signallens"
    secret_key: str = "dev-insecure-secret-change-me-before-any-deployment"
    session_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # --- Models -------------------------------------------------------------------------
    llm_provider: Literal["auto", "anthropic", "openai", "gemini", "none"] = "auto"
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

    # --- Demo lab -----------------------------------------------------------------------
    sandbox_enabled: bool = True
    # Show the demo-account shortcut on the sign-in page. Default: on outside production.
    demo_login: bool | None = None

    @property
    def demo_login_enabled(self) -> bool:
        return self.demo_login if self.demo_login is not None else self.env != "prod"

    # --- Outbound email for approved external shares (optional) --------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
