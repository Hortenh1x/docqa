"use client";

import type { DonePayload } from "@/lib/api/types";
import { formatCost, formatLatency, formatTokens } from "@/lib/format";

/** Confidence as a word, not a gauge — people read words. */
export function MetaLine({ done }: { done: DonePayload }) {
  const grounded = (done.confidence ?? 0) >= 0.6;
  const totalTokens =
    done.usage.prompt_tokens !== null && done.usage.completion_tokens !== null
      ? done.usage.prompt_tokens + done.usage.completion_tokens
      : null;

  return (
    <p className="font-data flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
      <span className={grounded ? "text-verify" : "text-pending"}>
        ● {grounded ? "grounded" : "partial"}
      </span>
      {done.confidence !== null && <span>confidence {done.confidence.toFixed(2)}</span>}
      <span>{formatTokens(totalTokens)} tokens</span>
      <span>{formatCost(done.usage.cost_usd)}</span>
      <span>{formatLatency(done.latency_ms)}</span>
    </p>
  );
}
