"""Workspace members and roles (owner | admin | member). See api/roles.py for what roles allow.

Adding someone by email:
- an existing account in the same organisation is added to the workspace;
- an email with no account yet creates an *invited* account in this organisation with no
  password (``auth_provider="oidc"``). The person signs in with single sign-on, and the SSO
  callback links their identity to this account by email. Without SSO configured an invited
  account cannot sign in yet;
- an email that belongs to another organisation is refused (409).

Workspace access itself is organisation-wide in v1, so removing someone resets their role:
if they open the workspace again they come back as a ``member``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, session
from signallens.api.roles import OWNER, ensure_member, is_approver
from signallens.db.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/workspaces/{wid}/members", tags=["members"])


def member_out(m: WorkspaceMember, u: User, me: uuid.UUID) -> S.Member:
    return S.Member(user_id=str(u.id), name=u.name, email=u.email, role=m.role, auth_provider=u.auth_provider,
                    is_you=u.id == me, joined_at=m.created_at)


async def _require_manager(s: AsyncSession, ws: Workspace, who: Principal) -> WorkspaceMember:
    me = await ensure_member(s, ws, who.user.id)
    if not is_approver(me.role):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can manage members.")
    return me


async def _target(s: AsyncSession, ws: Workspace, uid: uuid.UUID) -> tuple[WorkspaceMember, User]:
    row = (await s.execute(select(WorkspaceMember, User).join(User, User.id == WorkspaceMember.user_id)
                           .where(WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == uid))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="This person is not a member of the workspace.")
    return row[0], row[1]


async def _owner_count(s: AsyncSession, ws: Workspace) -> int:
    return (await s.execute(select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.workspace_id == ws.id, WorkspaceMember.role == OWNER))).scalar_one()


@router.get("", response_model=list[S.Member])
async def list_members(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                       who: Principal = Depends(current)):
    await ensure_member(s, ws, who.user.id)
    rank = {"owner": 0, "admin": 1, "member": 2}
    rows = (await s.execute(select(WorkspaceMember, User).join(User, User.id == WorkspaceMember.user_id)
                            .where(WorkspaceMember.workspace_id == ws.id))).all()
    rows = sorted(rows, key=lambda r: (rank.get(r[0].role, 3), r[1].name.lower(), r[1].email))
    return [member_out(m, u, who.user.id) for m, u in rows]


@router.post("", response_model=S.Member)
async def add_member(body: S.MemberAdd, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                     who: Principal = Depends(current)):
    me = await _require_manager(s, ws, who)
    if body.role == OWNER and me.role != OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can make someone an owner.")
    email = body.email.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None and user.org_id != who.org.id:
        raise HTTPException(status_code=409, detail="This email belongs to an account in another organisation.")
    if user is None:
        name = (body.name or "").strip() or local.replace(".", " ").replace("_", " ").title()
        user = User(id=uuid.uuid4(), org_id=who.org.id, email=email, name=name, password_hash=None,
                    auth_provider="oidc")
        s.add(user)
        await s.flush()
    elif await s.get(WorkspaceMember, (ws.id, user.id)) is not None:
        raise HTTPException(status_code=409, detail=f"{user.name} is already a member. Change their role instead.")
    m = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=body.role)
    s.add(m)
    await s.flush()
    return member_out(m, user, who.user.id)


@router.patch("/{uid}", response_model=S.Member)
async def change_role(uid: uuid.UUID, body: S.MemberPatch, ws: Workspace = Depends(get_workspace),
                      s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    me = await _require_manager(s, ws, who)
    m, u = await _target(s, ws, uid)
    if m.role == body.role:
        return member_out(m, u, who.user.id)
    if (body.role == OWNER or m.role == OWNER) and me.role != OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can grant or remove the owner role.")
    if m.role == OWNER and await _owner_count(s, ws) <= 1:
        raise HTTPException(status_code=409, detail="A workspace needs at least one owner. Make someone else "
                                                    "an owner first.")
    m.role = body.role
    await s.flush()
    return member_out(m, u, who.user.id)


@router.delete("/{uid}", status_code=204)
async def remove_member(uid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                        who: Principal = Depends(current)):
    leaving = uid == who.user.id
    me = await ensure_member(s, ws, who.user.id) if leaving else await _require_manager(s, ws, who)
    m, _ = await _target(s, ws, uid)
    if m.role == OWNER and not leaving and me.role != OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can remove another owner.")
    if m.role == OWNER and await _owner_count(s, ws) <= 1:
        raise HTTPException(status_code=409, detail="A workspace needs at least one owner. Make someone else "
                                                    "an owner first.")
    await s.delete(m)
    return Response(status_code=204)
