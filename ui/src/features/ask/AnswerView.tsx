"use client";

import { Fragment } from "react";
import type { Source } from "@/lib/api/types";

const CITATION_SPLIT = /(\[\d+\])/g;

/** Inline [n] marks render as small "library stamps" — the one signature element. */
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
            <button
              key={index}
              type="button"
              onClick={(e) => onOpenSource(n, e.currentTarget)}
              aria-label={`Source ${n}: ${source.filename}${
                source.pages ? `, pages ${source.pages[0]}–${source.pages[1]}` : ""
              }`}
              title={`${source.filename}${source.section ? ` — ${source.section}` : ""}`}
              className="font-data mx-0.5 inline-block -translate-y-px rounded border border-stamp/70 px-1 text-[11px] leading-4 text-stamp hover:bg-stamp/10"
            >
              {n}
            </button>
          );
        })}
      </p>
    </div>
  );
}
