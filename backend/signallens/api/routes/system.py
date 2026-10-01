"""Health and non-secret configuration (which providers are active; never the keys)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from signallens import __version__
from signallens.api import schemas as S
from signallens.api.deps import services, session
from signallens.db.base import utcnow
from signallens.db.models import WorkerHeartbeat
from signallens.notify.email import email_status
from signallens.runtime.services import Services

router = APIRouter(tags=["system"])


@router.get("/health", response_model=S.Health)
async def health(s: AsyncSession = Depends(session)) -> S.Health:
    try:
        await s.execute(text("SELECT 1"))
        db = True
        seen = (await s.execute(select(func.max(WorkerHeartbeat.seen_at)))).scalar_one_or_none()
    except Exception:
        db, seen = False, None
    return S.Health(ok=db, db=db, worker_seen_at=seen if seen and seen > utcnow() - timedelta(days=30) else seen)


@router.get("/system/config", response_model=S.SystemConfig)
async def system_config(svc: Services = Depends(services)) -> S.SystemConfig:
    llm = svc.llm
    search = svc.search
    mail = email_status(svc.settings)
    return S.SystemConfig(
        llm=S.LLMConfig(provider=llm.provider_name if llm else None, fast_model=llm.fast_model if llm else None,
                        reasoning_model=llm.reasoning_model if llm else None, configured=llm is not None),
        search=S.SearchConfig(provider=getattr(search, "name", None) if search else None, configured=search is not None),
        email=S.EmailConfig(provider=mail.provider, configured=mail.configured, sender=mail.sender,
                            digest_enabled=svc.settings.digest_email_enabled, reason=mail.reason),
        sandbox_enabled=svc.settings.sandbox_enabled,
        demo_login=svc.settings.demo_login_enabled,
        version=__version__,
    )
