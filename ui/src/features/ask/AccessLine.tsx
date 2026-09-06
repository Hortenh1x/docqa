"use client";

import { LockIcon } from "@/components/LockIcon";
import { joinNames, labelName } from "@/lib/access";
import type { AccessInfo } from "@/lib/api/types";

/** One quiet line under the sources: what the current role did not get to see.
 *  Rendered only in reveal mode with something actually hidden. */
export function AccessLine({ access }: { access: AccessInfo | null }) {
  const hidden = access?.hidden_passages ?? 0;
  if (!access || hidden === 0) return null;
  const groups = joinNames((access.hidden_labels ?? []).map(labelName));
  return (
    <p className="font-data flex items-center gap-1.5 text-xs text-ink-soft">
      <LockIcon />
      <span>
        {hidden} more {hidden === 1 ? "passage is" : "passages are"} restricted
        {groups ? ` to ${groups}` : ""} — switch role to include {hidden === 1 ? "it" : "them"}.
      </span>
    </p>
  );
}
