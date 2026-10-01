"""Small helpers shared by pipeline stages."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from dateutil import parser as dateparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.base import utcnow
from signallens.db.models import Evidence, Team, Workspace


def today_str() -> str:
    return utcnow().strftime("%Y-%m-%d (%A)")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def evidence_lines(session: AsyncSession, claim_id: uuid.UUID, *, limit: int = 12) -> list[str]:
    rows = (await session.execute(
        select(Evidence).where(Evidence.claim_id == claim_id).order_by(Evidence.created_at).limit(limit)
    )).scalars().all()
    return [
        f"[{e.stance}] {e.publisher} ({e.source_class}{', archived' if e.is_archive else ''}"
        f"{'' if e.quote_verified else ', quote not verified'}): “{e.quote[:400]}”"
        for e in rows
    ]


async def team_names(session: AsyncSession, workspace_id: uuid.UUID) -> list[str]:
    rows = (await session.execute(select(Team.name).where(Team.workspace_id == workspace_id).order_by(Team.name)))
    return [r[0] for r in rows]


async def workspace(session: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise LookupError(f"workspace {workspace_id} not found")
    return ws
