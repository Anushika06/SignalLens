"""Briefs requested through the hosted API: run with the app's services and keep a record.

The synchronous endpoint and the ``agent_brief`` background job share
:func:`run_stored_brief`, so a brief is produced and stored the same way however it was
requested. Briefs are not retried automatically: a failed run is usually a provider limit,
and repeating several minutes of model calls would only make that worse.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import update

from signallens.brief.agent import run_brief
from signallens.brief.models import BriefInput, BriefResult
from signallens.brief.reader import make_reader, reader_mode
from signallens.brief.runner import tavily_for
from signallens.db.base import utcnow
from signallens.db.models import AgentBrief
from signallens.db.session import transaction
from signallens.runtime.jsonutil import jsonable
from signallens.runtime.services import Services

log = logging.getLogger(__name__)


async def execute_brief(services: Services, inputs: BriefInput, *, on_step=None) -> BriefResult:
    llm = services.require_llm()
    search = services.require_search()
    settings = services.settings
    reader = make_reader(reader_mode(), fetcher=services.fetcher, tavily=tavily_for(search, settings))
    return await run_brief(inputs, llm=llm, search=search, reader=reader, wayback=services.wayback,
                           deadline_s=settings.brief_timeout_s, on_step=on_step, app_url=settings.public_app_url)


async def create_brief(services: Services, inputs: BriefInput, *, client: str | None, status: str) -> uuid.UUID:
    brief_id = uuid.uuid4()
    async with transaction(services.session_factory) as s:
        s.add(AgentBrief(id=brief_id, status=status, input=inputs.model_dump(), client=(client or "")[:120] or None,
                         trace=[]))
    return brief_id


async def run_stored_brief(services: Services, brief_id: uuid.UUID) -> dict[str, Any]:
    """Run the brief stored as ``brief_id`` and save its outcome. Never raises for run failures."""
    async with transaction(services.session_factory) as s:
        row = await s.get(AgentBrief, brief_id)
        if row is None:
            return {"skipped": "brief not found"}
        if row.status in ("succeeded", "failed"):
            return {"skipped": f"already {row.status}"}
        row.status = "running"
        inputs = BriefInput.model_validate(row.input)
    steps: list[dict[str, Any]] = []

    async def progress(step: dict[str, Any]) -> None:
        steps.append(step)
        async with transaction(services.session_factory) as s:
            await s.execute(update(AgentBrief).where(AgentBrief.id == brief_id).values(trace=jsonable(list(steps))))

    try:
        result = await execute_brief(services, inputs, on_step=progress)
    except Exception as e:
        log.exception("agent brief %s failed", brief_id)
        async with transaction(services.session_factory) as s:
            await s.execute(update(AgentBrief).where(AgentBrief.id == brief_id).values(
                status="failed", error=f"{type(e).__name__}: {e}"[:2000], finished_at=utcnow()))
        return {"status": "failed", "error": type(e).__name__}
    async with transaction(services.session_factory) as s:
        await s.execute(update(AgentBrief).where(AgentBrief.id == brief_id).values(
            status="succeeded", markdown=result.markdown, result=jsonable(result.data), trace=jsonable(result.trace),
            finished_at=utcnow()))
    return {"status": "succeeded", "brief_id": str(brief_id)}
