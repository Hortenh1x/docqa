"use client";

import { useQuery } from "@tanstack/react-query";
import { getUsage } from "@/lib/api/client";
import { formatCost, formatTokens } from "@/lib/format";

function BigNumber({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card">
      <div className="font-data text-3xl">{value}</div>
      <div className="mt-1 text-xs text-ink-soft">{label}</div>
    </div>
  );
}

export default function UsagePage() {
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
        <p className="font-data mt-1 text-xs text-ink-soft">last {data.days} days</p>
      </div>

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
      </div>

      {data.avg_latency_ms !== null && (
        <p className="font-data text-xs text-ink-soft">
          avg latency {data.avg_latency_ms}ms
        </p>
      )}
    </div>
  );
}
