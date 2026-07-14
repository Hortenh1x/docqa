"use client";

import type { DonePayload } from "@/lib/api/types";
import { formatCost, formatLatency, formatTokens } from "@/lib/format";

/** Confidence as a word, not a gauge — people read words. Format per the design plan:
 * `● grounded · confidence 0.91 · 2.3k tokens · $0.0007 · 1.8s` */
export function MetaLine({ done }: { done: DonePayload }) {
  const grounded = (done.confidence ?? 0) >= 0.6;
  const totalTokens =
    done.usage.prompt_tokens !== null && done.usage.completion_tokens !== null
      ? done.usage.prompt_tokens + done.usage.completion_tokens
      : null;

  const rest = [
    done.confidence !== null ? `confidence ${done.confidence.toFixed(2)}` : null,
    `${formatTokens(totalTokens)} tokens`,
    formatCost(done.usage.cost_usd),
    formatLatency(done.latency_ms),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <p className="font-data text-xs text-ink-soft">
      <span className={grounded ? "text-verify" : "text-pending"}>
        ● {grounded ? "grounded" : "partial"}
      </span>
      {" · "}
      {rest}
    </p>
  );
}
