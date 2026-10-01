"""Sign up, sign in, sign out, and who am I."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, session
from signallens.api.security import COOKIE_NAME, hash_password, issue_token, verify_password
from signallens.db.models import Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user: User, org: Organization) -> S.Me:
    return S.Me(user=S.UserOut(id=str(user.id), email=user.email, name=user.name),
                org=S.OrgOut(id=str(org.id), name=org.name))


def _set_cookie(request: Request, response: Response, user: User) -> None:
    settings = request.app.state.services.settings
    token = issue_token(user.id, user.org_id, secret=settings.secret_key, days=settings.session_days)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.env == "prod",
                        max_age=settings.session_days * 86400, path="/")


@router.post("/signup", response_model=S.Me)
async def signup(body: S.SignupIn, request: Request, response: Response, s: AsyncSession = Depends(session)) -> S.Me:
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if (await s.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    org = Organization(id=uuid.uuid4(), name=body.org_name.strip())
    user = User(id=uuid.uuid4(), org_id=org.id, email=email, name=body.name.strip(),
                password_hash=hash_password(body.password))
    s.add_all([org, user])
    await s.flush()
    _set_cookie(request, response, user)
    return _me(user, org)


@router.post("/login", response_model=S.Me)
async def login(body: S.LoginIn, request: Request, response: Response, s: AsyncSession = Depends(session)) -> S.Me:
    user = (await s.execute(select(User).where(User.email == body.email.strip().lower()))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    org = await s.get(Organization, user.org_id)
    _set_cookie(request, response, user)
    return _me(user, org)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=S.Me)
async def me(who: Principal = Depends(current)) -> S.Me:
    return _me(who.user, who.org)
