"""Command line: ``signallens <command>``.

    migrate      apply database migrations
    seed-demo    create the demo login and demo-lab pages (--lab also creates a lab workspace)
    api          run the HTTP API (uvicorn)
    worker       run the background worker (jobs + scheduler)
    dev          API with an in-process worker (single command for local use)
    run-jobs     process queued jobs until the queue is idle, then exit
    config       show which model/search providers are configured (never prints keys)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from signallens.config import BACKEND_DIR, get_settings


def _logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "trafilatura", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


async def _services():
    from signallens.db.session import make_engine, make_session_factory
    from signallens.runtime.services import build_services

    settings = get_settings()
    engine = make_engine(settings.database_url)
    return engine, build_services(settings, make_session_factory(engine))


async def seed_demo(lab: bool, reset_pages: bool) -> None:
    from signallens.db.session import transaction
    from signallens.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo_user, seed_lab_workspace, seed_sandbox

    engine, svc = await _services()
    try:
        async with transaction(svc.session_factory) as s:
            org, user, created = await seed_demo_user(s)
            pages = await seed_sandbox(s, reset=reset_pages)
            ws = await seed_lab_workspace(s, org, user) if lab else None
        print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD} ({'created' if created else 'already existed'})")
        print(f"Demo-lab pages seeded/reset: {pages}")
        if ws:
            print(f"Demo-lab workspace created: {ws.name} — baseline jobs queued (run the worker).")
    finally:
        await svc.aclose()
        await engine.dispose()


async def run_worker() -> None:
    from signallens.jobs.worker import Worker

    engine, svc = await _services()
    worker = Worker(svc)
    try:
        await worker.run()
    finally:
        await svc.aclose()
        await engine.dispose()


async def run_jobs(schedule: bool) -> None:
    from signallens.jobs.worker import Worker

    engine, svc = await _services()
    try:
        n = await Worker(svc, run_scheduler=False).run_until_idle(schedule=schedule)
        print(f"Processed {n} job(s).")
    finally:
        await svc.aclose()
        await engine.dispose()


def show_config() -> None:
    from signallens.runtime.services import build_gateway, build_search

    settings = get_settings()
    llm = build_gateway(settings)
    search = build_search(settings)
    print(f"database: {settings.database_url.split('@')[-1]}")
    print(f"model provider: {llm.provider_name if llm else 'NOT CONFIGURED'}"
          + (f" (fast={llm.fast_model}, reasoning={llm.reasoning_model})" if llm else ""))
    print(f"search provider: {getattr(search, 'name', type(search).__name__) if search else 'NOT CONFIGURED'}")
    print(f"robots.txt respected: {settings.respect_robots}; demo lab: {settings.sandbox_enabled}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="signallens", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    seed = sub.add_parser("seed-demo")
    seed.add_argument("--lab", action="store_true", help="also create the Nimbus Pay demo-lab workspace")
    seed.add_argument("--reset-pages", action="store_true", help="restore demo-lab pages to their original text")
    for name in ("api", "dev"):
        p = sub.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8000)
        p.add_argument("--reload", action="store_true")
    sub.add_parser("worker")
    rj = sub.add_parser("run-jobs")
    rj.add_argument("--schedule", action="store_true", help="also enqueue due source checks first")
    sub.add_parser("config")
    args = parser.parse_args(argv)
    _logging(args.verbose)

    if args.cmd == "migrate":
        migrate()
    elif args.cmd == "seed-demo":
        asyncio.run(seed_demo(args.lab, args.reset_pages))
    elif args.cmd in ("api", "dev"):
        import uvicorn

        if args.cmd == "dev":
            os.environ["SL_RUN_WORKER_IN_API"] = "true"
            get_settings.cache_clear()
        uvicorn.run("signallens.api.app:app", host=args.host, port=args.port, reload=args.reload,
                    log_level="info")
    elif args.cmd == "worker":
        try:
            asyncio.run(run_worker())
        except KeyboardInterrupt:
            pass
    elif args.cmd == "run-jobs":
        asyncio.run(run_jobs(args.schedule))
    elif args.cmd == "config":
        show_config()


if __name__ == "__main__":
    main()
