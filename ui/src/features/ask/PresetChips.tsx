"use client";

/** One preset per corpus trick: plain, table, version conflict, guaranteed refusal. */
export const PRESETS = [
  "How many days can I work from another EU country per year?",
  "What's the daily allowance for a business trip to France?",
  "How many vacation days do employees get?",
  "What is the company sabbatical policy?",
];

export function PresetChips({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="flex max-w-xl flex-wrap justify-center gap-2">
      {PRESETS.map((preset) => (
        <button
          key={preset}
          type="button"
          onClick={() => onPick(preset)}
          className="rounded-full border border-hairline bg-sheet px-3.5 py-1.5 text-sm text-ink-soft shadow-card hover:border-stamp/40 hover:text-ink"
        >
          {preset}
        </button>
      ))}
    </div>
  );
}
