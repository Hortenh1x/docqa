"use client";

import { useQuery } from "@tanstack/react-query";
import { DailyBudget } from "@/features/account/DailyBudget";
import { useAccount } from "@/features/account/context";
import { ACCOUNTS_ENABLED, getUsage } from "@/lib/api/client";
import { formatCost, formatDate, formatTokens } from "@/lib/format";

function BigNumber({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card">
      <div className="font-data text-3xl">{value}</div>
      <div className="mt-1 text-xs text-ink-soft">{label}</div>
    </div>
  );
}

export default function UsagePage() {
  const { session } = useAccount();
  const usage = useQuery({ queryKey: ["usage", 30], queryFn: () => getUsage(30) });

  if (usage.isLoading) {
    return <p className="py-16 text-center text-sm text-ink-soft">Loading usage…</p>;
  }
  if (!usage.data) {
    return <p className="py-16 text-center text-sm text-ink-soft">Usage unavailable.</p>;
  }

  const data = usage.data;
  const totalTokens = data.prompt_tokens + data.completion_tokens;
  const maxDaily = Math.max(1, ...data.daily.map((d) => d.queries));

  return (
    <div className="flex flex-col gap-6 py-8">
      <div>
        <h1 className="font-display text-2xl tracking-tight">Usage</h1>
        {!ACCOUNTS_ENABLED && <p className="font-data mt-1 text-xs text-ink-soft">last {data.days} days</p>}
        {ACCOUNTS_ENABLED && <p className="mt-2 text-sm text-ink-soft">{session?.user ? "Your account queries, including public collections." : "Guest queries from your current IP address."}</p>}
      </div>

      <DailyBudget />

      {ACCOUNTS_ENABLED && <h2 className="font-display text-xl">Queries · last {data.days} days</h2>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <BigNumber label={`queries (${data.refused} refused)`} value={String(data.queries)} />
        <BigNumber label="tokens" value={formatTokens(totalTokens)} />
        <BigNumber label="cost" value={formatCost(data.cost_usd)} />
      </div>

      <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card">
        <p className="mb-3 text-xs text-ink-soft">queries per day</p>
        {data.daily.length === 0 ? (
          <p className="font-display py-6 text-center text-xl text-ink-soft">
            No queries yet.
          </p>
        ) : (
          <div
            className="flex h-16 items-end gap-1"
            role="img"
            aria-label={`Daily queries sparkline over the last ${data.days} days`}
          >
            {data.daily.map((day) => (
              <div
                key={day.date}
                title={`${day.date}: ${day.queries} queries · ${formatCost(day.cost_usd)}`}
                className="min-w-2 flex-1 rounded-t-[2px] bg-stamp/70"
                style={{ height: `${Math.max(8, (day.queries / maxDaily) * 100)}%` }}
              />
            ))}
          </div>
        )}
        {data.daily.length > 0 && (
          <div className="font-data mt-1.5 flex justify-between text-[11px] text-ink-soft">
            <span>{formatDate(data.daily[0].date)}</span>
            <span>peak {maxDaily} / day</span>
            <span>{formatDate(data.daily[data.daily.length - 1].date)}</span>
          </div>
        )}
      </div>

      {data.avg_latency_ms !== null && (
        <p className="font-data text-xs text-ink-soft">
          avg latency {data.avg_latency_ms}ms
        </p>
      )}
    </div>
  );
}
