"""Demo lab: fictional pages that can be edited to demonstrate change detection on demand."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, session
from signallens.db.base import utcnow
from signallens.db.models import SandboxPage

router = APIRouter(prefix="/sandbox/pages", tags=["sandbox"])


def _enabled(request: Request) -> None:
    if not request.app.state.services.settings.sandbox_enabled:
        raise HTTPException(status_code=404, detail="Demo lab is disabled")


def _out(p: SandboxPage) -> S.SandboxPageOut:
    return S.SandboxPageOut(slug=p.slug, title=p.title, html=p.html, updated_at=p.updated_at)


@router.get("", response_model=list[S.SandboxPageOut], dependencies=[Depends(_enabled)])
async def pages(s: AsyncSession = Depends(session), _: Principal = Depends(current)):
    return [_out(p) for p in (await s.execute(select(SandboxPage).order_by(SandboxPage.slug))).scalars()]


@router.get("/{slug}", response_model=S.SandboxPageOut, dependencies=[Depends(_enabled)])
async def page(slug: str, s: AsyncSession = Depends(session), _: Principal = Depends(current)):
    p = await s.get(SandboxPage, slug)
    if p is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return _out(p)


@router.put("/{slug}", response_model=S.SandboxPageOut, dependencies=[Depends(_enabled)])
async def put_page(slug: str, body: S.SandboxPageIn, s: AsyncSession = Depends(session), _: Principal = Depends(current)):
    p = await s.get(SandboxPage, slug)
    if p is None:
        p = SandboxPage(slug=slug, title=body.title or slug, html=body.html)
        s.add(p)
    else:
        p.html = body.html
        if body.title:
            p.title = body.title
        p.updated_at = utcnow()
    await s.flush()
    return _out(p)
