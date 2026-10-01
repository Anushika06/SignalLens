"use client";

import { useState } from "react";
import { KeyRound, Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";

import { ToneBadge } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import { ListSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState, errorMessage } from "@/components/common/states";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { api, paths } from "@/lib/api";
import { revalidate, useMembers, useSsoConfig, useWorkspace } from "@/lib/hooks";
import type { WorkspaceMember, WorkspaceRole } from "@/lib/types";

const ROLES: { value: WorkspaceRole; label: string; description: string }[] = [
  { value: "owner", label: "Owner", description: "Approves external actions and manages members, including owners." },
  { value: "admin", label: "Admin", description: "Approves external actions and manages members." },
  { value: "member", label: "Member", description: "Sees everything and can request external actions." },
];
const ROLE_LABEL = Object.fromEntries(ROLES.map((role) => [role.value, role.label])) as Record<WorkspaceRole, string>;

async function refresh(wid: string) {
  await revalidate((path) => path === paths.members(wid) || path === paths.workspace(wid));
  await revalidate(`${paths.workspace(wid)}/approvals`);
}

function RoleSelect({
  id,
  value,
  onChange,
  allowOwner,
  disabled,
  label,
  size = "sm",
}: {
  id: string;
  value: WorkspaceRole;
  onChange: (role: WorkspaceRole) => void;
  allowOwner: boolean;
  disabled?: boolean;
  label: string;
  size?: "sm" | "default";
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as WorkspaceRole)} disabled={disabled}>
      <SelectTrigger id={id} size={size} className="w-28" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.filter((role) => allowOwner || role.value !== "owner" || value === "owner").map((role) => (
          <SelectItem key={role.value} value={role.value} disabled={role.value === "owner" && !allowOwner}>
            {role.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function RemoveMember({ wid, member }: { wid: string; member: WorkspaceMember }) {
  const [removing, setRemoving] = useState(false);
  const label = member.is_you ? "Leave workspace" : `Remove ${member.name}`;

  async function remove() {
    setRemoving(true);
    try {
      await api.members.remove(wid, member.user_id);
      toast.success(member.is_you ? "You left the workspace's member list" : `Removed ${member.name}`);
      await refresh(wid);
    } catch (error) {
      toast.error(member.is_you ? "Couldn't leave" : "Couldn't remove the member", {
        description: errorMessage(error),
      });
    } finally {
      setRemoving(false);
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label} disabled={removing}>
          {removing ? <Spinner /> : <Trash2 aria-hidden="true" />}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{member.is_you ? "Leave this workspace?" : `Remove ${member.name}?`}</AlertDialogTitle>
          <AlertDialogDescription>
            {member.is_you ? "You" : "They"} lose the {ROLE_LABEL[member.role].toLowerCase()} role here. Everyone in
            your organisation can still open the workspace; opening it again rejoins as a member.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void remove()}>
            {member.is_you ? "Leave" : "Remove"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function MemberRow({
  wid,
  member,
  canManage,
  iAmOwner,
  ssoProvider,
}: {
  wid: string;
  member: WorkspaceMember;
  canManage: boolean;
  iAmOwner: boolean;
  ssoProvider: string;
}) {
  const [saving, setSaving] = useState(false);
  // Admins can't change an owner; nobody but an owner grants the owner role (the API enforces both).
  const editable = canManage && (iAmOwner || member.role !== "owner");

  async function changeRole(role: WorkspaceRole) {
    if (role === member.role) return;
    setSaving(true);
    try {
      await api.members.setRole(wid, member.user_id, role);
      toast.success(`${member.is_you ? "You are" : `${member.name} is`} now ${ROLE_LABEL[role].toLowerCase()}`);
      await refresh(wid);
    } catch (error) {
      toast.error("Couldn't change the role", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-5">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <span className="truncate">{member.name}</span>
          {member.is_you ? <ToneBadge tone="blue">You</ToneBadge> : null}
          {member.auth_provider === "oidc" ? (
            <ToneBadge tone="gray" icon={KeyRound} title={`Signs in with ${ssoProvider} single sign-on`}>
              SSO
            </ToneBadge>
          ) : null}
        </p>
        <p className="truncate text-xs text-muted-foreground">{member.email}</p>
      </div>
      <div className="flex items-center gap-1">
        {saving ? <Spinner className="mr-1" /> : null}
        {editable ? (
          <RoleSelect
            id={`member-role-${member.user_id}`}
            value={member.role}
            onChange={(role) => void changeRole(role)}
            allowOwner={iAmOwner}
            disabled={saving}
            label={`Role of ${member.name}`}
          />
        ) : (
          <ToneBadge tone={member.role === "member" ? "gray" : "green"}>{ROLE_LABEL[member.role]}</ToneBadge>
        )}
        {editable || member.is_you ? <RemoveMember wid={wid} member={member} /> : null}
      </div>
    </li>
  );
}

function AddMemberForm({ wid, iAmOwner, ssoHint }: { wid: string; iAmOwner: boolean; ssoHint: string }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<WorkspaceRole>("member");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(value)) {
      setError("Enter a valid email address.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const added = await api.members.add(wid, { email: value, role });
      toast.success(`Added ${added.name} as ${ROLE_LABEL[added.role].toLowerCase()}`);
      setEmail("");
      setRole("member");
      await refresh(wid);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-2 border-t bg-muted/30 px-4 py-3 sm:px-5">
      <Field data-invalid={error ? true : undefined}>
        <FieldLabel htmlFor="member-add-email">Add a person</FieldLabel>
        <div className="flex flex-wrap gap-2">
          <Input
            id="member-add-email"
            type="email"
            inputMode="email"
            autoComplete="off"
            placeholder="colleague@yourcompany.com"
            className="min-w-48 flex-1"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              if (error) setError(null);
            }}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "member-add-error" : "member-add-hint"}
          />
          <RoleSelect
            id="member-add-role"
            value={role}
            onChange={setRole}
            allowOwner={iAmOwner}
            label="Role for the new member"
            size="default"
          />
          <Button type="submit" disabled={pending}>
            {pending ? <Spinner /> : <UserPlus aria-hidden="true" />}
            Add
          </Button>
        </div>
        {error ? (
          <FieldError id="member-add-error">{error}</FieldError>
        ) : (
          <FieldDescription id="member-add-hint">{ssoHint}</FieldDescription>
        )}
      </Field>
    </form>
  );
}

/** Who is in the workspace and who may approve external actions (owners and admins). */
export function MembersSection({ wid }: { wid: string }) {
  const { data: members, error, isLoading, mutate } = useMembers(wid);
  const { data: workspace } = useWorkspace(wid);
  const { data: sso } = useSsoConfig();
  const canManage = workspace?.can_manage_members ?? false;
  const iAmOwner = workspace?.my_role === "owner";
  const provider = sso?.provider_name ?? "single sign-on";
  const ssoHint = sso?.enabled
    ? `Someone in your organisation is added directly. A new email gets an account that signs in with ${provider}.`
    : "Someone in your organisation is added directly. A new email gets an invited account, which can sign in once single sign-on is set up.";

  return (
    <Section
      id="members"
      title="Members & roles"
      description="Owners and admins approve actions that leave the company (emails, external shares, webhooks) and manage members. Nobody approves their own request unless they're the only approver."
    >
      {error && !members ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : isLoading || !members ? (
        <ListSkeleton rows={2} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          {members.length === 0 ? (
            <EmptyState icon={Users} title="No members yet" description="Add the people who should approve actions." />
          ) : (
            <ul className="divide-y" aria-label="Workspace members">
              {members.map((member) => (
                <MemberRow
                  key={member.user_id}
                  wid={wid}
                  member={member}
                  canManage={canManage}
                  iAmOwner={iAmOwner}
                  ssoProvider={provider}
                />
              ))}
            </ul>
          )}
          {canManage ? (
            <AddMemberForm wid={wid} iAmOwner={iAmOwner} ssoHint={ssoHint} />
          ) : (
            <p className="border-t bg-muted/30 px-4 py-3 text-xs text-muted-foreground sm:px-5">
              Only owners and admins can add people or change roles.
            </p>
          )}
        </div>
      )}
    </Section>
  );
}
