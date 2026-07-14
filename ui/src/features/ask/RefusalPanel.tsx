"use client";

import { PRESETS } from "./PresetChips";

/** Refusal is a first-class state: amber (honesty), never red (not an error). */
export function RefusalPanel({ onPick }: { onPick: (question: string) => void }) {
  const alternatives = PRESETS.slice(0, 3);
  return (
    <div className="rounded-[10px] border border-pending/40 bg-pending/10 px-5 py-4">
      <p className="font-medium text-ink">Not found in the documents.</p>
      <p className="mt-1 text-sm text-ink-soft">
        The collection doesn&rsquo;t contain information about this — so no answer was invented.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {alternatives.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => onPick(preset)}
            className="rounded-full border border-hairline bg-sheet px-3 py-1 text-xs text-ink-soft hover:text-ink"
          >
            {preset}
          </button>
        ))}
      </div>
    </div>
  );
}
