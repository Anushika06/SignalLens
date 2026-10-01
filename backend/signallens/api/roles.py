"""Workspace roles and the approver rules for external actions.

Roles: ``owner`` | ``admin`` | ``member``. The person who creates a workspace is its owner.
Only owners and admins may approve or reject an :class:`Approval`. Whoever requested an action
may not decide it while another owner or admin exists in the workspace; a sole approver may,
and the decision note records that it was self-approved. Actions proposed by an agent
(``requested_by_user_id`` is None) can be decided by any owner or admin.

Access to a workspace is organisation-wide in v1: anyone in the organisation who opens a
workspace becomes a ``member`` of it. Membership rows carry the role.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.models import Approval, User, Workspace, WorkspaceMember

OWNER, ADMIN, MEMBER = "owner", "admin", "member"
ROLES = (OWNER, ADMIN, MEMBER)
APPROVER_ROLES = frozenset({OWNER, ADMIN})
SELF_APPROVED_SUFFIX = "(self-approved: sole approver)"


def is_approver(role: str | None) -> bool:
    return role in APPROVER_ROLES


async def ensure_member(s: AsyncSession, ws: Workspace, user_id: uuid.UUID) -> WorkspaceMember:
    """The user's membership row, created as ``member`` on first visit.

    A workspace that somehow has no owner (data from before roles existed) gets its
    earliest member promoted to owner, so there is always someone who can approve.
    """
    m = await s.get(WorkspaceMember, (ws.id, user_id))
    if m is None:
        m = WorkspaceMember(workspace_id=ws.id, user_id=user_id, role=MEMBER)
        s.add(m)
        await s.flush()
    has_owner = (await s.execute(select(WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == ws.id, WorkspaceMember.role == OWNER).limit(1))).first()
    if has_owner is None:
        first = (await s.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id)
                                 .order_by(WorkspaceMember.created_at, WorkspaceMember.user_id).limit(1))).scalar_one()
        first.role = OWNER
        await s.flush()
    return m


@dataclass
class ApproverContext:
    """What the viewer may do with approvals in one workspace."""

    user_id: uuid.UUID
    my_role: str
    approver_ids: set[uuid.UUID]
    names: dict[uuid.UUID, str] = field(default_factory=dict)

    @property
    def can_approve(self) -> bool:
        return is_approver(self.my_role)

    def is_self_request(self, a: Approval) -> bool:
        return a.requested_by_user_id is not None and a.requested_by_user_id == self.user_id

    def sole_approver(self) -> bool:
        return not (self.approver_ids - {self.user_id})

    def check(self, a: Approval) -> tuple[bool, str | None]:
        """(may decide, reason if not). Decided approvals cannot be decided again."""
        if a.status != "pending":
            return False, None
        if not self.can_approve:
            return False, (f"Only workspace owners and admins can approve or reject external actions "
                           f"(your role: {self.my_role}).")
        if self.is_self_request(a) and not self.sole_approver():
            return False, "You requested this action, so another owner or admin has to decide it."
        return True, None


async def approver_context(s: AsyncSession, ws: Workspace, user_id: uuid.UUID) -> ApproverContext:
    me = await ensure_member(s, ws, user_id)
    rows = (await s.execute(select(WorkspaceMember.user_id, WorkspaceMember.role)
                            .where(WorkspaceMember.workspace_id == ws.id))).all()
    approvers = {uid for uid, role in rows if is_approver(role)}
    return ApproverContext(user_id=user_id, my_role=me.role, approver_ids=approvers)


async def load_requester_names(s: AsyncSession, ctx: ApproverContext, approvals: list[Approval]) -> None:
    ids = {a.requested_by_user_id for a in approvals if a.requested_by_user_id} - set(ctx.names)
    if ids:
        for uid, name in (await s.execute(select(User.id, User.name).where(User.id.in_(ids)))).all():
            ctx.names[uid] = name
