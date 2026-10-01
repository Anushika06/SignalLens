"""FastAPI application factory. All routes live under ``/api``."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from signallens import __version__
from signallens.api.routes import (
    approvals,
    auth,
    monitoring,
    plans,
    reports,
    runs,
    sandbox,
    system,
    workspaces,
    world,
)
from signallens.config import Settings, get_settings
from signallens.db.session import make_engine, make_session_factory
from signallens.runtime.services import Services, build_services

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.env == "prod" and (settings.secret_key.startswith("dev-insecure") or len(settings.secret_key) < 32):
        raise RuntimeError("Set SL_SECRET_KEY to a random value of at least 32 characters in production.")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        svc = services
        if svc is None:
            engine = make_engine(settings.database_url)
            svc = build_services(settings, make_session_factory(engine))
        app.state.services = svc
        worker_task = worker = None
        if settings.run_worker_in_api:
            from signallens.jobs.worker import Worker

            worker = Worker(svc)
            worker_task = asyncio.create_task(worker.run())
            log.info("in-process worker started")
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()
                await asyncio.gather(worker_task, return_exceptions=True)
            if services is None:
                await svc.aclose()
                if engine is not None:
                    await engine.dispose()

    app = FastAPI(title="SignalLens API", version=__version__, lifespan=lifespan)
    if services is not None:
        app.state.services = services  # tests drive the app without running lifespan
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    api = APIRouter(prefix="/api")
    for module in (system, auth, workspaces, plans, reports, world, monitoring, runs, approvals, sandbox):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
