"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { ACCOUNTS_ENABLED, getBudget } from "@/lib/api/client";

export function BudgetNotice() {
  const budget = useQuery({ queryKey: ["budget"], queryFn: getBudget, enabled: ACCOUNTS_ENABLED, staleTime: 15_000, retry: false });
  const resetAt = budget.data?.enabled ? budget.data.reset_at : null;
  useEffect(() => {
    if (!resetAt) return;
    const delay = new Date(resetAt).getTime() - Date.now() + 1000;
    if (delay <= 0) return;
    const timer = setTimeout(() => void budget.refetch(), Math.min(delay, 86_400_000));
    return () => clearTimeout(timer);
  }, [resetAt, budget.refetch]);
  if (!ACCOUNTS_ENABLED) return null;
  if (budget.isError) return <p role="status" className="text-xs text-ink-soft">Budget temporarily unavailable.</p>;
  if (!budget.data?.enabled) return null;
  const data = budget.data;
  return (
    <div className="border-t border-hairline px-4 py-2 text-xs text-ink-soft">
      <div className="mx-auto flex max-w-[1128px] flex-wrap items-baseline gap-x-3 gap-y-1">
        <span role="status" className="font-data text-ink">${Number(data.remaining_usd).toFixed(2)} remaining / ${Number(data.limit_usd).toFixed(2)} per day</span>
        <span>Resets at 00:00 UTC.</span>
        <span>Guest use carries over after sign-in. Shared networks share the IP allowance.</span>
      </div>
    </div>
  );
}
