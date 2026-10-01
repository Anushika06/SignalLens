import { Clock } from "lucide-react";

import { ToneBadge, WithTooltip } from "@/components/common/badges";
import { Spinner } from "@/components/ui/spinner";
import { RUN_STATUS } from "@/lib/labels";
import type { RunStatus } from "@/lib/types";

/** Run status with a spinner while running and an explanation for "Budget exhausted". */
export function RunStatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const meta = RUN_STATUS[status];
  const badge = (
    <ToneBadge tone={meta.tone} className={className}>
      {status === "running" ? <Spinner aria-hidden="true" /> : null}
      {status === "queued" ? <Clock aria-hidden="true" /> : null}
      {meta.label}
    </ToneBadge>
  );
  return meta.description ? <WithTooltip content={meta.description}>{badge}</WithTooltip> : badge;
}
