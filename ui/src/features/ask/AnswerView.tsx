"use client";

import { Fragment } from "react";
import type { Source } from "@/lib/api/types";
import { formatPages } from "@/lib/format";

const CITATION_SPLIT = /(\[\d+\])/g;

/** Inline [n] marks render as small "library stamps" — the one signature element.
 * Hover/focus shows a mini source card; click opens the full source panel. */
export function AnswerView({
  answer,
  sources,
  streaming,
  onOpenSource,
}: {
  answer: string;
  sources: Source[];
  streaming: boolean;
  onOpenSource: (n: number, trigger: HTMLElement | null) => void;
}) {
  const byN = new Map(sources.map((s) => [s.n, s]));
  const parts = answer.split(CITATION_SPLIT);

  return (
    <div
      className={`rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card ${
        streaming ? "caret" : ""
      }`}
    >
      <p className="whitespace-pre-wrap text-[15px] leading-7">
        {parts.map((part, index) => {
          const match = /^\[(\d+)\]$/.exec(part);
          if (!match) return <Fragment key={index}>{part}</Fragment>;
          const n = Number(match[1]);
          const source = byN.get(n);
          if (!source) return <Fragment key={index}>{part}</Fragment>;
          return (
            <span key={index} className="group relative inline-block">
              <button
                type="button"
                onClick={(e) => onOpenSource(n, e.currentTarget)}
                aria-label={`Source ${n}: ${source.filename}${
                  source.pages ? `, pages ${source.pages[0]}–${source.pages[1]}` : ""
                }`}
                className="font-data mx-0.5 inline-block -translate-y-px rounded border border-stamp/70 px-1 text-[11px] leading-4 text-stamp hover:bg-stamp/10"
              >
                {n}
              </button>
              {/* hover mini-card; click still opens the full drawer */}
              <span
                role="presentation"
                className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-1.5 w-64 -translate-x-1/2 rounded-[10px] border border-hairline bg-sheet p-2.5 text-left shadow-card opacity-0 transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
              >
                <span className="font-data block truncate text-xs text-ink">
                  {source.filename}
                </span>
                <span className="font-data mt-0.5 block text-[11px] text-ink-soft">
                  {formatPages(source.pages) ?? "no pages"}
                  {source.section ? ` · ${source.section}` : ""}
                </span>
                <span className="mt-1 block text-xs leading-5 text-ink-soft">
                  {source.snippet.slice(0, 120)}
                  {source.snippet.length > 120 ? "…" : ""}
                </span>
              </span>
            </span>
          );
        })}
      </p>
    </div>
  );
}
