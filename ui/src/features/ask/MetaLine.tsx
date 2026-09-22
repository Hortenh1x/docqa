"use client";

import { roleName } from "@/lib/access";
import type { DonePayload } from "@/lib/api/types";
import { formatCost, formatLatency, formatTokens } from "@/lib/format";

/** Keep the answer status and original role visible; diagnostics are optional detail. */
export function MetaLine({ done, role }: { done: DonePayload; role?: string | null }) {
  const grounded = (done.confidence ?? 0) >= 0.6;
  const totalTokens =
    done.usage.prompt_tokens !== null && done.usage.completion_tokens !== null
      ? done.usage.prompt_tokens + done.usage.completion_tokens
      : null;

  const details = [
    done.confidence !== null ? `confidence ${done.confidence.toFixed(2)}` : null,
    `${formatTokens(totalTokens)} tokens`,
    formatCost(done.usage.cost_usd),
    formatLatency(done.latency_ms),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="font-data flex flex-wrap items-start gap-x-4 text-xs text-ink-soft">
      <p className="min-h-11 py-3">
        <span className={grounded ? "text-verify" : "text-pending"}>
          ● {grounded ? "grounded" : "partial"}
        </span>
        {role && <> · as {roleName(role)}</>}
      </p>
      <details className="min-w-0 flex-1 basis-40 open:basis-full">
        <summary className="min-h-11 cursor-pointer rounded-[6px] py-3 hover:text-ink">
          Answer details
        </summary>
        <p className="pb-2">{details}</p>
      </details>
    </div>
  );
}
