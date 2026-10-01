"""Request dependencies: database session, current user, workspace access control."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api.security import COOKIE_NAME, read_token
from signallens.db.models import Organization, User, Workspace
from signallens.runtime.services import Services


def services(request: Request) -> Services:
    return request.app.state.services


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.services.session_factory() as s:
        try:
            yield s
            await s.commit()
        except BaseException:
            await s.rollback()
            raise


@dataclass
class Principal:
    user: User
    org: Organization


async def current(request: Request, s: AsyncSession = Depends(session)) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    ids = read_token(token, secret=request.app.state.services.settings.secret_key) if token else None
    if ids is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = await s.get(User, ids[0])
    org = await s.get(Organization, ids[1])
    if user is None or org is None or user.org_id != org.id:
        raise HTTPException(status_code=401, detail="Session is no longer valid")
    return Principal(user=user, org=org)


async def workspace_for(wid: uuid.UUID, s: AsyncSession, who: Principal) -> Workspace:
    ws = await s.get(Workspace, wid)
    if ws is None or ws.org_id != who.org.id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


async def get_workspace(wid: uuid.UUID, s: AsyncSession = Depends(session), who: Principal = Depends(current)) -> Workspace:
    return await workspace_for(wid, s, who)
