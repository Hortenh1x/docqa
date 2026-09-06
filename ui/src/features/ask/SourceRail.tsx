"use client";

import { LockIcon } from "@/components/LockIcon";
import { labelName } from "@/lib/access";
import type { Source } from "@/lib/api/types";
import { formatPages } from "@/lib/format";

/** Sources appear BEFORE the answer text — you see where it will come from first. */
export function SourceRail({
  sources,
  activeN,
  onOpen,
}: {
  sources: Source[];
  activeN: number | null;
  onOpen: (n: number, trigger: HTMLElement | null) => void;
}) {
  return (
    <div role="list" aria-label="Sources" className="flex gap-2 overflow-x-auto pb-1">
      {sources.map((source) => (
        <button
          key={source.n}
          role="listitem"
          type="button"
          onClick={(e) => onOpen(source.n, e.currentTarget)}
          aria-label={`Source ${source.n}: ${source.filename}${
            source.pages ? `, pages ${source.pages[0]}–${source.pages[1]}` : ""
          }`}
          className={`min-w-44 shrink-0 rounded-[10px] border bg-sheet p-2.5 text-left shadow-card transition-colors ${
            activeN === source.n ? "border-stamp" : "border-hairline hover:border-stamp/40"
          }`}
        >
          <div className="flex items-baseline gap-2">
            <span className="font-data rounded border border-stamp/60 px-1 text-[11px] leading-4 text-stamp">
              {source.n}
            </span>
            <span className="font-data truncate text-xs text-ink">{source.filename}</span>
          </div>
          <div className="font-data mt-1 text-[11px] text-ink-soft">
            {formatPages(source.pages) ?? "no pages"}
            {source.section ? ` · ${source.section}` : ""}
          </div>
          {source.access_label !== "all" && (
            <span className="font-data mt-1.5 inline-flex items-center gap-1 rounded border border-hairline px-1 text-[10px] leading-4 text-ink-soft">
              <LockIcon className="h-2.5 w-2.5" />
              {labelName(source.access_label)}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
