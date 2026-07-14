"use client";

import { useEffect, useRef } from "react";
import type { Source } from "@/lib/api/types";
import { formatPages } from "@/lib/format";

/** Right-hand "document passport": file, pages, section, score, highlighted snippet. */
export function SourceDrawer({
  source,
  onClose,
}: {
  source: Source | null;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!source) return;
    closeRef.current?.focus();

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      // minimal focus trap
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        "button, a[href], [tabindex]:not([tabindex='-1'])",
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [source, onClose]);

  if (!source) return null;

  const citation = `${source.filename}${
    source.pages ? `, ${formatPages(source.pages)}` : ""
  }${source.section ? ` — ${source.section}` : ""}`;

  return (
    <>
      <button
        type="button"
        aria-label="Close source panel"
        onClick={onClose}
        className="fixed inset-0 z-20 cursor-default bg-ink/20 min-[1100px]:hidden"
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Source ${source.n}: ${source.filename}`}
        className="fixed bottom-0 right-0 top-0 z-30 flex w-full max-w-[400px] flex-col gap-4 overflow-y-auto border-l border-hairline bg-sheet p-5 shadow-card max-sm:top-auto max-sm:max-h-[75vh] max-sm:rounded-t-[10px] max-sm:border-t"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-data rounded border border-stamp/60 px-1.5 py-0.5 text-xs text-stamp">
              {source.n}
            </span>
            <h2 className="font-data break-all text-sm">{source.filename}</h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-[6px] border border-hairline px-2 py-0.5 text-sm text-ink-soft hover:text-ink"
          >
            Esc
          </button>
        </div>

        <dl className="font-data grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
          {source.pages && (
            <>
              <dt className="text-ink-soft">Pages</dt>
              <dd>{formatPages(source.pages)}</dd>
            </>
          )}
          {source.section && (
            <>
              <dt className="text-ink-soft">Section</dt>
              <dd>{source.section}</dd>
            </>
          )}
          <dt className="text-ink-soft">Relevance</dt>
          <dd>{source.score.toFixed(3)}</dd>
        </dl>

        <blockquote className="rounded-[6px] border border-hairline bg-paper p-3 text-sm leading-6">
          <mark className="bg-stamp/10 text-ink">{source.snippet}</mark>
          {source.snippet.length >= 300 ? "…" : ""}
        </blockquote>

        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(citation)}
          className="self-start rounded-[6px] border border-hairline px-3 py-1.5 text-sm text-ink-soft hover:border-stamp/40 hover:text-ink"
        >
          Copy citation
        </button>
      </aside>
    </>
  );
}
