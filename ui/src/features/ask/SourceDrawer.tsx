"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCollections } from "@/app/providers";
import { labelName } from "@/lib/access";
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
  const { selected } = useCollections();
  const panelRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const backdropPress = useRef(false);
  const [modal, setModal] = useState(false);
  const close = useCallback(() => {
    // Release native modal inertness before the caller restores the trigger's focus.
    panelRef.current?.close();
    onClose();
  }, [onClose]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!source || !panel) return;
    const media = window.matchMedia("(min-width: 1100px)");
    const originalOverflow = document.body.style.overflow;
    const update = () => {
      const focused = document.activeElement;
      panel.close();
      setModal(!media.matches);
      document.body.style.overflow = media.matches ? originalOverflow : "hidden";
      if (media.matches) panel.show();
      else panel.showModal();
      if (focused instanceof HTMLElement && panel.contains(focused)) focused.focus();
      else closeRef.current?.focus();
    };
    update();
    media.addEventListener("change", update);
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      // Native inertness blocks the page; wrap Tab as well so it stays in the sheet.
      if (e.key === "Tab" && panel.matches(":modal")) {
        const focusables = panel.querySelectorAll<HTMLElement>(
          "button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
        );
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      media.removeEventListener("change", update);
      document.removeEventListener("keydown", handler);
      panel.close();
      document.body.style.overflow = originalOverflow;
    };
  }, [source, close]);

  if (!source) return null;

  const citation = `${source.filename}${
    source.pages ? `, ${formatPages(source.pages)}` : ""
  }${source.section ? ` — ${source.section}` : ""}`;

  return (
      <dialog
        ref={panelRef}
        aria-modal={modal ? "true" : undefined}
        aria-label={`Source ${source.n}: ${source.filename}`}
        onCancel={e => { e.preventDefault(); close(); }}
        onPointerDown={e => {
          const r = e.currentTarget.getBoundingClientRect();
          backdropPress.current = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
        }}
        onClick={e => {
          const r = e.currentTarget.getBoundingClientRect();
          if (modal && backdropPress.current && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) close();
          backdropPress.current = false;
        }}
        className="source-dialog fixed bottom-0 left-auto right-0 top-0 z-30 m-0 h-full max-h-dvh w-full max-w-[400px] flex-col gap-4 overflow-y-auto border-l border-hairline bg-sheet p-5 text-ink shadow-card open:flex max-sm:top-auto max-sm:h-auto max-sm:max-h-[75dvh] max-sm:rounded-t-[10px] max-sm:border-t"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-data rounded border border-stamp/60 px-1.5 py-0.5 text-xs text-stamp">
              {source.n}
            </span>
            <h2 className="font-data break-all text-sm">{source.filename}</h2>
            {selected && (
              <span className="rounded-full border border-hairline bg-paper px-2 py-0.5 text-[11px] text-ink-soft">
                {selected.name}
              </span>
            )}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={close}
            aria-label="Close"
            className="min-h-11 shrink-0 rounded-[6px] border border-hairline px-3 py-2 text-sm text-ink-soft hover:text-ink active:bg-paper"
          >
            Close
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
          <dt className="text-ink-soft">Access</dt>
          <dd>
            {selected?.owned ? "Private · only your account" : source.access_label === "all"
              ? "All staff"
              : `${labelName(source.access_label)} only`}
          </dd>
        </dl>

        <blockquote className="rounded-[6px] border border-hairline bg-paper p-3 text-sm leading-6">
          <mark className="bg-stamp/12 text-ink">{source.snippet}</mark>
          {source.snippet.length >= 300 ? "…" : ""}
        </blockquote>

        <CitationCopy key={citation} citation={citation} />
      </dialog>
  );
}

function CitationCopy({ citation }: { citation: string }) {
  const [state, setState] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  const copying = useRef(false);
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-disabled={state === "copying"}
        onClick={async () => {
          if (copying.current) return;
          copying.current = true;
          setState("copying");
          try {
            await navigator.clipboard.writeText(citation);
            setState("copied");
          } catch {
            setState("failed");
          } finally {
            copying.current = false;
          }
        }}
        className="min-h-11 self-start rounded-[6px] border border-hairline px-3 py-2 text-sm text-ink-soft hover:border-stamp/40 hover:text-ink active:bg-paper aria-disabled:opacity-40"
      >
        {state === "copying" ? "Copying…" : state === "copied" ? "Copied" : "Copy citation"}
      </button>
      <p role="status" className="text-xs text-ink-soft">{state === "copied" ? "Citation copied." : ""}</p>
      {state === "failed" && <>
        <p role="alert" className="text-sm text-error">Couldn&apos;t copy. Select the citation below and copy it manually.</p>
        <label className="text-sm">Citation
          <textarea readOnly value={citation} rows={3} onFocus={e => e.currentTarget.select()} className="mt-1 w-full rounded-[6px] border border-control bg-sheet p-2 text-sm" />
        </label>
      </>}
    </div>
  );
}
