"""Postgres-backed job queue.

Why not Celery + Redis (spec review C14): jobs are inserted in the *same transaction* as
the state change that causes them (an event and its investigation job commit together or
not at all), the worker is asyncio-native like the rest of the runtime, there is one less
service to operate, and jobs are ordinary rows the UI can show as live agent activity.

Claiming uses ``FOR UPDATE SKIP LOCKED`` so any number of workers can poll safely.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.base import utcnow
from signallens.db.models import Job

LIVE_STATUSES = ("queued", "running")

# Lower number = claimed first. Interactive work beats scheduled background work.
PRIORITY_INTERACTIVE = 10
PRIORITY_PIPELINE = 50
PRIORITY_BACKGROUND = 100


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    workspace_id: uuid.UUID | None = None,
    run_at: datetime | None = None,
    priority: int = PRIORITY_PIPELINE,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
) -> uuid.UUID | None:
    """Add a job in the caller's transaction. Returns None if a live duplicate exists."""
    stmt = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            payload=payload or {},
            workspace_id=workspace_id,
            run_at=run_at or utcnow(),
            priority=priority,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
            status="queued",
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"], index_where=text("status IN ('queued', 'running')")
        )
        .returning(Job.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


_CLAIM_SQL = text(
    """
    UPDATE jobs SET status = 'running', locked_by = :worker, locked_at = now(),
                    attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND run_at <= now()
        ORDER BY priority, run_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id
    """
)


async def claim(session: AsyncSession, worker_id: str) -> Job | None:
    job_id = (await session.execute(_CLAIM_SQL, {"worker": worker_id})).scalar_one_or_none()
    if job_id is None:
        return None
    return await session.get(Job, job_id)


async def complete(session: AsyncSession, job_id: uuid.UUID, result: dict[str, Any] | None = None) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="succeeded", finished_at=utcnow(), result=result, locked_by=None)
    )


def retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(0, attempt - 1), 1800))


async def fail(session: AsyncSession, job: Job, error: str, *, retryable: bool = True) -> None:
    """Record a failure; requeue with backoff while attempts remain."""
    if retryable and job.attempts < job.max_attempts:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(status="queued", run_at=utcnow() + retry_delay(job.attempts), last_error=error[:4000],
                    locked_by=None)
        )
    else:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(status="failed", finished_at=utcnow(), last_error=error[:4000], locked_by=None)
        )


async def requeue_stale(session: AsyncSession, *, older_than: timedelta = timedelta(minutes=20)) -> int:
    """Return jobs whose worker died mid-run to the queue."""
    result = await session.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_at < utcnow() - older_than)
        .values(status="queued", locked_by=None, last_error="requeued after stale lock")
    )
    return result.rowcount or 0


async def pending_count(session: AsyncSession, workspace_id: uuid.UUID, kinds: tuple[str, ...]) -> int:
    rows = await session.execute(
        select(Job.id).where(Job.workspace_id == workspace_id, Job.kind.in_(kinds), Job.status.in_(LIVE_STATUSES))
    )
    return len(rows.all())
