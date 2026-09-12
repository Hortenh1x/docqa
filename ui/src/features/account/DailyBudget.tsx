"use client";

import { useQuery } from "@tanstack/react-query";
import { ACCOUNTS_ENABLED, getBudget } from "@/lib/api/client";
import { formatCost } from "@/lib/format";

export function DailyBudget() {
  const budget = useQuery({
    queryKey: ["budget"],
    queryFn: getBudget,
    enabled: ACCOUNTS_ENABLED,
    staleTime: 15_000,
    retry: false,
  });
  if (!ACCOUNTS_ENABLED) return null;
  if (budget.isPending) return <p role="status" className="text-sm text-ink-soft">Loading daily budget…</p>;
  if (budget.isError) return <p role="status" className="text-sm text-ink-soft">Daily budget temporarily unavailable.</p>;
  if (!budget.data.enabled) return null;
  const data = budget.data;
  const amounts = [
    ["Settled spend", data.spent_usd],
    ["Pending reservations", data.reserved_usd],
    ["Remaining", data.remaining_usd],
    ["Daily limit", data.limit_usd],
  ];

  return (
    <section aria-labelledby="daily-budget-heading" className="border-y border-hairline py-5">
      <h2 id="daily-budget-heading" className="font-display text-xl">Daily budget</h2>
      <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
        {amounts.map(([label, amount]) => (
          <div key={label}>
            <dt className="text-xs text-ink-soft">{label}</dt>
            <dd className="font-data mt-1 text-lg">{Number(amount) === 0 ? "$0.00" : formatCost(Number(amount))}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs leading-5 text-ink-soft">
        Settled spend includes completed AI usage. Pending reservations are held for
        in-flight or unconfirmed usage and already reduce the remaining allowance.
      </p>
      <p className="mt-1 text-xs text-ink-soft">
        Resets <time dateTime={data.reset_at}>{new Date(data.reset_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</time>.
      </p>
    </section>
  );
}
