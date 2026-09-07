"use client";

import { LockIcon } from "@/components/LockIcon";
import { joinNames, labelName } from "@/lib/access";
import type { AccessInfo } from "@/lib/api/types";

/** One quiet line under the sources of an answered question: restricted passages that
 *  scored at least as well as the best one the role could see — the ones that might
 *  have changed the answer. Loosely related restricted passages are not mentioned here;
 *  the refusal panel handles the case where nothing visible answered at all. */
export function AccessLine({ access }: { access: AccessInfo | null }) {
  const strong = access?.hidden_outranking ?? 0;
  if (!access || strong === 0) return null;
  const groups = joinNames((access.hidden_labels ?? []).map(labelName));
  return (
    <p className="font-data flex items-center gap-1.5 text-xs text-ink-soft">
      <LockIcon />
      <span>
        {strong} restricted {strong === 1 ? "passage" : "passages"}
        {groups ? ` (${groups})` : ""} ranked at least as high as what you can see — switch
        role to include {strong === 1 ? "it" : "them"}.
      </span>
    </p>
  );
}
