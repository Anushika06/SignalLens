import { hostname } from "@/lib/format";
import { APPROVAL_ACTION } from "@/lib/labels";
import type { Approval } from "@/lib/types";

/**
 * Approval payloads are free-form JSON proposed by an agent (or created by a user share).
 * These helpers read the common shapes defensively so the UI can show a readable preview
 * — an email, a share, a webhook post — and fall back to raw JSON for anything else.
 */

/** First non-empty string (or list of strings) found under any of `keys`. */
export function payloadText(payload: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === "string" && item.trim() !== "");
      if (items.length) return items.join(", ");
    }
  }
  return null;
}

export type PayloadView =
  | { kind: "email"; to: string; cc: string | null; subject: string | null; body: string | null }
  | { kind: "share"; recipient: string; note: string | null; reportTitle: string | null }
  | { kind: "webhook"; url: string; body: unknown }
  | { kind: "raw" };

export function describePayload(approval: Approval): PayloadView {
  const payload = approval.payload ?? {};
  if (approval.action_type === "send_external_email") {
    const to = payloadText(payload, "to", "recipient", "email");
    if (to) {
      return {
        kind: "email",
        to,
        cc: payloadText(payload, "cc"),
        subject: payloadText(payload, "subject"),
        body: payloadText(payload, "body", "text", "message"),
      };
    }
  }
  if (approval.action_type === "share_report_externally") {
    const recipient = payloadText(payload, "recipient", "to", "email");
    if (recipient) {
      return {
        kind: "share",
        recipient,
        note: payloadText(payload, "note", "message"),
        reportTitle: payloadText(payload, "report_title", "title"),
      };
    }
  }
  if (approval.action_type === "post_external_webhook") {
    const url = payloadText(payload, "url", "endpoint", "webhook_url");
    if (url) return { kind: "webhook", url, body: payload.body ?? payload.payload ?? payload.data ?? null };
  }
  return { kind: "raw" };
}

/** One plain sentence saying exactly what approving will do. */
export function approveConsequence(approval: Approval): string {
  const view = describePayload(approval);
  switch (view.kind) {
    case "email":
      return `SignalLens will send this email to ${view.to}. Sent emails can't be recalled.`;
    case "share":
      return `SignalLens will share this intelligence card with ${view.recipient}.`;
    case "webhook":
      return `SignalLens will post this payload to ${hostname(view.url) || view.url}.`;
    case "raw":
      return `SignalLens will carry out this action: ${APPROVAL_ACTION[approval.action_type].label.toLowerCase()}.`;
  }
}

/** Verb for the confirm button: "Approve and send", "Approve and share"… */
export function approveVerb(approval: Approval): string {
  switch (approval.action_type) {
    case "send_external_email":
      return "Approve and send";
    case "share_report_externally":
      return "Approve and share";
    case "post_external_webhook":
      return "Approve and post";
  }
}

/** An error message from an approval's `result`, if the action failed. */
export function resultError(approval: Approval): string | null {
  return approval.result ? payloadText(approval.result, "error", "detail", "message") : null;
}
