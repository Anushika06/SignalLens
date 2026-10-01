"""Human-in-the-loop queue for consequential actions. Approving enqueues execution.

Who may decide is defined in api/roles.py: owners and admins, never the requester while another
owner or admin exists.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, session
from signallens.api.roles import SELF_APPROVED_SUFFIX, approver_context, load_requester_names
from signallens.api.views import approval_out
from signallens.db.base import utcnow
from signallens.db.models import Approval, Workspace
from signallens.jobs.queue import PRIORITY_INTERACTIVE, enqueue

router = APIRouter(prefix="/workspaces/{wid}/approvals", tags=["approvals"])


@router.get("", response_model=list[S.Approval])
async def approvals(status: str | None = None, ws: Workspace = Depends(get_workspace),
                    s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    q = select(Approval).where(Approval.workspace_id == ws.id)
    if status:
        q = q.where(Approval.status == status)
    rows = list((await s.execute(q.order_by(Approval.created_at.desc()).limit(200))).scalars())
    ctx = await approver_context(s, ws, who.user.id)
    await load_requester_names(s, ctx, rows)
    return [approval_out(a, ctx) for a in rows]


@router.post("/{aid}/decide", response_model=S.Approval)
async def decide(aid: uuid.UUID, body: S.DecideIn, ws: Workspace = Depends(get_workspace),
                 s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    a = await s.get(Approval, aid, with_for_update=True)
    if a is None or a.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    if a.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {a.status}")
    ctx = await approver_context(s, ws, who.user.id)
    allowed, reason = ctx.check(a)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason or "You can't decide this action")
    a.status = "approved" if body.decision == "approve" else "rejected"
    note = (body.note or "").strip() or None
    if a.status == "approved" and ctx.is_self_request(a):  # allowed only for a sole approver
        note = f"{note} {SELF_APPROVED_SUFFIX}" if note else SELF_APPROVED_SUFFIX
    a.decided_by, a.decided_at, a.decision_note = who.user.email, utcnow(), note
    if a.status == "approved":
        await enqueue(s, "execute_approval", {"approval_id": str(a.id)}, workspace_id=ws.id,
                      priority=PRIORITY_INTERACTIVE, dedupe_key=f"approval:{a.id}", max_attempts=1)
    await load_requester_names(s, ctx, [a])
    return approval_out(a, ctx)
