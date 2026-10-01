"""Background worker: claims jobs, runs pipeline stages, and schedules source checks.

One process runs N consumers plus a scheduler tick. Several processes can run side by
side; ``SKIP LOCKED`` claiming and dedupe keys keep them from stepping on each other.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from signallens.db.base import utcnow
from signallens.db.models import Job, Source, WorkerHeartbeat, Workspace
from signallens.db.session import transaction
from signallens.jobs import queue
from signallens.pipeline.collection import backfill_source, baseline_source, check_source
from signallens.pipeline.delivery import execute_approval, route_report, send_digest
from signallens.pipeline.investigate import investigate_event
from signallens.pipeline.planning import run_planning
from signallens.pipeline.report import analyze_event
from signallens.runtime.services import NotConfigured, Services

log = logging.getLogger(__name__)

Handler = Callable[[Services, dict[str, Any]], Awaitable[Any]]


def _uuid(payload: dict[str, Any], key: str) -> uuid.UUID:
    return uuid.UUID(str(payload[key]))


HANDLERS: dict[str, Handler] = {
    "plan_monitoring": lambda svc, p: run_planning(svc, _uuid(p, "policy_id")),
    "baseline_source": lambda svc, p: baseline_source(svc, _uuid(p, "source_id")),
    "backfill_source": lambda svc, p: backfill_source(svc, _uuid(p, "source_id")),
    "check_source": lambda svc, p: check_source(svc, _uuid(p, "source_id")),
    "investigate_event": lambda svc, p: investigate_event(svc, _uuid(p, "event_id")),
    "analyze_event": lambda svc, p: analyze_event(svc, _uuid(p, "event_id"), historical=bool(p.get("historical"))),
    "route_report": lambda svc, p: route_report(svc, _uuid(p, "report_id")),
    "send_digest": lambda svc, p: send_digest(svc, _uuid(p, "workspace_id")),
    "execute_approval": lambda svc, p: execute_approval(svc, _uuid(p, "approval_id")),
}

BASELINE_KINDS = ("baseline_source", "backfill_source")


class Worker:
    def __init__(self, services: Services, *, concurrency: int | None = None, poll_s: float = 1.0,
                 run_scheduler: bool = True, worker_id: str | None = None):
        self.services = services
        self.concurrency = concurrency or services.settings.worker_concurrency
        self.poll_s = poll_s
        self.run_scheduler = run_scheduler
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        log.info("worker %s starting (%d consumers)", self.worker_id, self.concurrency)
        tasks = [asyncio.create_task(self._consume(i)) for i in range(self.concurrency)]
        tasks.append(asyncio.create_task(self._heartbeat()))
        if self.run_scheduler:
            tasks.append(asyncio.create_task(self._schedule()))
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run_until_idle(self, *, max_jobs: int = 500, schedule: bool = False) -> int:
        """Process queued jobs until none are runnable (used by tests and the CLI)."""
        done = 0
        while done < max_jobs:
            if schedule:
                await self.tick()
            if not await self._run_one():
                break
            done += 1
        return done

    async def _consume(self, n: int) -> None:
        while not self._stop.is_set():
            try:
                ran = await self._run_one()
            except Exception:  # never let a consumer die
                log.exception("consumer %d crashed; continuing", n)
                ran = False
            if not ran:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_s)
                except TimeoutError:
                    pass

    async def _run_one(self) -> bool:
        async with transaction(self.services.session_factory) as s:
            job = await queue.claim(s, self.worker_id)
            if job is None:
                return False
            job_id, kind, payload, workspace_id = job.id, job.kind, dict(job.payload), job.workspace_id
        handler = HANDLERS.get(kind)
        try:
            if handler is None:
                raise NotConfigured(f"no handler for job kind {kind!r}")
            result = await handler(self.services, payload)
            async with transaction(self.services.session_factory) as s:
                await queue.complete(s, job_id, result if isinstance(result, dict) else {"result": str(result)})
        except NotConfigured as e:
            async with transaction(self.services.session_factory) as s:
                await queue.fail(s, await s.get(Job, job_id), str(e), retryable=False)
        except Exception as e:
            log.exception("job %s (%s) failed", job_id, kind)
            async with transaction(self.services.session_factory) as s:
                await queue.fail(s, await s.get(Job, job_id), f"{type(e).__name__}: {e}", retryable=True)
        if kind in BASELINE_KINDS and workspace_id:
            await self._refresh_workspace_status(workspace_id)
        return True

    async def _refresh_workspace_status(self, workspace_id: uuid.UUID) -> None:
        async with transaction(self.services.session_factory) as s:
            pending = await queue.pending_count(s, workspace_id, BASELINE_KINDS)
            ws = await s.get(Workspace, workspace_id)
            if ws and ws.status == "baselining" and pending == 0:
                ws.status = "monitoring"

    async def _heartbeat(self) -> None:
        while not self._stop.is_set():
            try:
                async with transaction(self.services.session_factory) as s:
                    await s.execute(insert(WorkerHeartbeat).values(
                        worker_id=self.worker_id, seen_at=utcnow(), info={"concurrency": self.concurrency},
                    ).on_conflict_do_update(index_elements=["worker_id"], set_={"seen_at": utcnow()}))
            except Exception:
                log.debug("heartbeat failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=15)
            except TimeoutError:
                pass

    async def _schedule(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.services.settings.scheduler_tick_s)
            except TimeoutError:
                pass

    async def tick(self, now: datetime | None = None) -> int:
        """Enqueue checks for due sources, daily digests, and recover stale jobs."""
        now = now or utcnow()
        enqueued = 0
        async with transaction(self.services.session_factory) as s:
            await queue.requeue_stale(s)
            due = (await s.execute(
                select(Source).where(Source.active.is_(True), Source.next_check_at <= now)
                .order_by(Source.next_check_at).limit(100).with_for_update(skip_locked=True)
            )).scalars().all()
            for src in due:
                # A source whose baseline failed (site down, no search key yet) retries its baseline.
                kind = "check_source" if src.baselined else "baseline_source"
                if await queue.enqueue(s, kind, {"source_id": str(src.id)}, workspace_id=src.workspace_id,
                                       priority=queue.PRIORITY_BACKGROUND,
                                       dedupe_key=f"{'check' if src.baselined else 'baseline'}:{src.id}"):
                    enqueued += 1
                # Tentatively push the next check out; the check itself sets the real value.
                src.next_check_at = now + timedelta(minutes=max(5, src.current_interval_minutes))
            hour = self.services.settings.digest_hour_utc
            digest_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now >= digest_at:
                stale = (await s.execute(select(Workspace).where(
                    Workspace.status == "monitoring",
                    (Workspace.last_digest_at.is_(None)) | (Workspace.last_digest_at < digest_at),
                ))).scalars().all()
                for ws in stale:
                    await queue.enqueue(s, "send_digest", {"workspace_id": str(ws.id)}, workspace_id=ws.id,
                                        priority=queue.PRIORITY_BACKGROUND,
                                        dedupe_key=f"digest:{ws.id}:{digest_at.date().isoformat()}")
                    await s.execute(update(Workspace).where(Workspace.id == ws.id).values(last_digest_at=now))
        return enqueued
