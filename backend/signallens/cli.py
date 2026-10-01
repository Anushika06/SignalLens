"""Command line: ``signallens <command>``.

    migrate      apply database migrations
    seed-demo    create the demo login and demo-lab pages (--lab also creates a lab workspace)
    api          run the HTTP API (uvicorn)
    worker       run the background worker (jobs + scheduler)
    dev          API with an in-process worker (single command for local use)
    run-jobs     process queued jobs until the queue is idle, then exit
    config       show which model/search providers are configured (never prints keys)
    brief        one-shot intelligence brief on a company, printed as markdown (no database needed)
    aikart-run   aiKart "Try Me Now" entry point: /aikart/input.json -> /aikart/output.json
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
    from signallens.demo import (
        DEMO_ADMIN_EMAIL,
        DEMO_EMAIL,
        DEMO_PASSWORD,
        seed_demo_members,
        seed_demo_user,
        seed_lab_workspace,
        seed_sandbox,
    )

    engine, svc = await _services()
    try:
        async with transaction(svc.session_factory) as s:
            org, user, created = await seed_demo_user(s)
            pages = await seed_sandbox(s, reset=reset_pages)
            ws = await seed_lab_workspace(s, org, user) if lab else None
            await seed_demo_members(s, org, user)
        print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD} ({'created' if created else 'already existed'})")
        print(f"Second approver (admin): {DEMO_ADMIN_EMAIL} / {DEMO_PASSWORD}")
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
    from signallens.fetch.render import render_availability
    from signallens.notify.email import email_status

    mail = email_status(settings)
    print(f"email: {mail.label}" + (f" (from {mail.sender}; daily digest "
                                     f"{'on' if settings.digest_email_enabled else 'off'})" if mail.configured
                                    else f" - {mail.reason}"))
    available, detail = render_availability()
    state = ("enabled" if available else "enabled but UNAVAILABLE") if settings.render_js else "disabled"
    print(f"JavaScript rendering: {state} ({detail}{'' if settings.render_js else '; set SL_RENDER_JS=true to use'})")


async def run_brief_cli(args: argparse.Namespace) -> int:
    """``signallens brief``: run locally with configured keys, else delegate to SL_REMOTE_AGENT_URL."""
    import sys

    from signallens.brief.models import BriefInput
    from signallens.brief.runner import (
        NOT_CONFIGURED_HINT,
        RemoteError,
        build_local_tools,
        run_local,
        run_remote,
    )

    settings = get_settings()
    inputs = BriefInput(company=args.company, your_company=args.your_company, focus=args.focus,
                        language=args.language, months_back=args.months_back)
    data = None
    tools = build_local_tools(settings)
    if tools is not None:
        def progress(step: dict) -> None:
            print(f"  [{step['started_s']:6.1f}s] {step['name']} ({step['ms'] / 1000:.1f}s): {step['detail']}",
                  file=sys.stderr)

        try:
            result = await run_local(inputs, settings, tools, on_step=progress)
        finally:
            await tools.aclose()
        markdown, data = result.markdown, {"data": result.data, "trace": result.trace}
    elif settings.remote_agent_url:
        try:
            markdown = await run_remote(inputs, settings)
        except RemoteError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    else:
        print("error: no model/search keys configured and SL_REMOTE_AGENT_URL is not set.\n"
              + NOT_CONFIGURED_HINT.replace("**", ""), file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")  # Hindi briefs on Windows consoles
    print(markdown)
    _write_brief_files(args, markdown, data)
    return 0


def _write_brief_files(args: argparse.Namespace, markdown: str, data: dict | None) -> None:
    import json
    from pathlib import Path

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8", newline="\n")
    if args.json_out and data is not None:
        Path(args.json_out).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


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
    br = sub.add_parser("brief", help="one-shot intelligence brief (markdown)")
    br.add_argument("company", help="company name or website, e.g. Razorpay")
    br.add_argument("--for", dest="your_company", help="your company, e.g. 'Cashfree Payments, a payment gateway'")
    br.add_argument("--focus", default="Everything", help="Everything | Pricing & products | Regulatory & compliance "
                                                          "| Partnerships & funding | Leadership & hiring")
    br.add_argument("--language", default="English", help="English | Hindi")
    br.add_argument("--months-back", type=int, default=12)
    br.add_argument("--out", help="also write the markdown to this file")
    br.add_argument("--json", dest="json_out", help="write the structured result (data + trace) to this file")
    sub.add_parser("aikart-run", help="aiKart container entry point")
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
    elif args.cmd == "brief":
        raise SystemExit(asyncio.run(run_brief_cli(args)))
    elif args.cmd == "aikart-run":
        from signallens.brief.runner import aikart_main

        raise SystemExit(aikart_main())


if __name__ == "__main__":
    main()
