"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRole } from "@/app/providers";
import { LockIcon } from "@/components/LockIcon";
import { HighlightedPassage } from "@/features/ask/HighlightedPassage";
import { labelName } from "@/lib/access";
import { ApiError, fetchDocumentFile, fetchPassages } from "@/lib/api/client";
import type { DocumentOut, Passage, QuoteSpan } from "@/lib/api/types";
import { formatBytes, formatPages } from "@/lib/format";

const TEXT_MIMES = new Set(["text/markdown", "text/plain"]);
const WINDOW = 60;

export type ReaderMode = "passages" | "original";

/** The passage a citation points at: the reader opens on it and marks the quoted words. */
export interface ReaderHighlight {
  chunkId: number | null;
  chunkIndex: number | null;
  pages: [number, number] | null;
  quotes: QuoteSpan[];
}

/** Full-height reading panel. *Original* renders the file as uploaded (PDFs in the
 *  browser's viewer, MD/TXT as text); *Passages* renders the document's text in reading
 *  order — every format — and is where a citation's exact words are highlighted. */
export function DocumentViewer({
  doc,
  onClose,
  owner = false,
  highlight = null,
  initialMode = "original",
}: {
  doc: DocumentOut;
  onClose: () => void;
  owner?: boolean;
  highlight?: ReaderHighlight | null;
  initialMode?: ReaderMode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [mode, setMode] = useState<ReaderMode>(initialMode);

  const { role } = useRole();
  const file = useQuery({
    queryKey: ["document-file", doc.id, role],
    queryFn: () => fetchDocumentFile(doc.id, owner ? undefined : role),
    staleTime: Infinity,
    retry: false,
    enabled: mode === "original",
  });
  const fileError = file.error instanceof ApiError ? file.error : null;
  const restricted = fileError?.code === "document_restricted";
  const notReady = fileError?.code === "document_not_ready";

  const objectUrl = useMemo(
    () => (file.data ? URL.createObjectURL(file.data) : null),
    [file.data],
  );
  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [objectUrl]);

  const isText = TEXT_MIMES.has(doc.mime_type);
  const [text, setText] = useState<{ blob: Blob; value: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    const blob = file.data;
    if (blob && isText) {
      void blob.text().then((value) => {
        if (!cancelled) setText({ blob, value });
      });
    }
    return () => {
      cancelled = true;
    };
  }, [file.data, isText]);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      // Keep keyboard navigation inside the document reader.
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), a[href], iframe, [tabindex]:not([tabindex='-1'])",
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
    return () => {
      document.removeEventListener("keydown", handler);
      if (opener?.isConnected) opener.focus();
    };
  }, [onClose]);

  const isPdf = doc.mime_type === "application/pdf";
  // a citation opens the original PDF on its page
  const pdfFragment = `#toolbar=0&navpanes=0${highlight?.pages ? `&page=${highlight.pages[0]}` : ""}`;

  return (
    <>
      <button
        type="button"
        aria-label="Close reader"
        onClick={onClose}
        className="fixed inset-0 z-40 cursor-default bg-ink/20"
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Read ${doc.filename}`}
        className="fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-[760px] flex-col border-l border-hairline bg-sheet shadow-card max-sm:top-auto max-sm:max-h-[85vh] max-sm:rounded-t-[10px] max-sm:border-t"
      >
        <div className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-data truncate text-sm" title={doc.filename}>
              {doc.filename}
            </h2>
            <p className="font-data mt-0.5 text-[11px] text-ink-soft">
              {doc.page_count ? `${doc.page_count} p. · ` : ""}
              {doc.size_bytes > 0 ? formatBytes(doc.size_bytes) : "…"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div role="group" aria-label="View" className="flex rounded-[6px] border border-hairline">
              {(["passages", "original"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={mode === option}
                  onClick={() => setMode(option)}
                  className={`min-h-11 px-2.5 py-2 text-sm first:rounded-l-[6px] last:rounded-r-[6px] ${
                    mode === option ? "bg-paper text-ink" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {option === "passages" ? "Passages" : "Original"}
                </button>
              ))}
            </div>
            {mode === "original" && objectUrl && (
              <a
                href={objectUrl}
                download={doc.filename}
                className="inline-flex min-h-11 items-center rounded-[6px] border border-hairline px-2.5 py-2 text-sm text-ink-soft hover:border-stamp/40 hover:text-ink active:bg-paper"
              >
                Download
              </a>
            )}
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="min-h-11 rounded-[6px] border border-hairline px-3 py-2 text-sm text-ink-soft hover:text-ink active:bg-paper"
            >
              Close
            </button>
          </div>
        </div>

        {mode === "passages" && (
          <PassagesView doc={doc} owner={owner} highlight={highlight} />
        )}

        {mode === "original" && file.isPending && (
          <p className="p-5 text-sm text-ink-soft">Loading the file…</p>
        )}
        {mode === "original" && file.isError && restricted && (
          <p role="alert" className="p-5 text-sm text-ink-soft">
            This document holds a section restricted to another group — switch the role in
            the top bar to read it.
          </p>
        )}
        {mode === "original" && file.isError && notReady && (
          <p role="alert" className="p-5 text-sm text-ink-soft">
            {fileError?.problem.document_status === "failed"
              ? "Processing failed. This file is unavailable. Check the document status for details."
              : "This document is still being processed. Close the reader and try again when its status is ready."}
          </p>
        )}
        {mode === "original" && file.isError && !restricted && !notReady && (
          <p role="alert" className="p-5 text-sm text-error">
            Couldn&apos;t load the file.
          </p>
        )}

        {mode === "original" && isPdf && objectUrl && (
          <iframe
            title={doc.filename}
            // the browser's PDF toolbar would show the blob URL's id as the document name;
            // the panel header already names the file and offers the download
            src={`${objectUrl}${pdfFragment}`}
            className="min-h-0 w-full flex-1"
          />
        )}
        {mode === "original" && isText && file.isSuccess && text && text.blob === file.data && (
          <pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-5 py-4 font-sans text-sm leading-6">
            {text.value}
          </pre>
        )}
        {mode === "original" && !isPdf && !isText && objectUrl && (
          <p className="p-5 text-sm text-ink-soft">
            This format doesn&apos;t render in the browser — use Download above to read it
            locally, or switch to Passages for its text.
          </p>
        )}
      </aside>
    </>
  );
}

/** The document's chunks in reading order, a window at a time. Opened from a citation the
 *  window is centred on the cited chunk and its quoted words are marked. */
function PassagesView({
  doc,
  owner,
  highlight,
}: {
  doc: DocumentOut;
  owner: boolean;
  highlight: ReaderHighlight | null;
}) {
  const { role } = useRole();
  const around = highlight?.chunkIndex ?? null;
  const page = useQuery({
    queryKey: ["passages", doc.id, owner ? "owner" : role, around],
    queryFn: () =>
      fetchPassages(doc.id, {
        role: owner ? undefined : role,
        around: around ?? undefined,
        limit: WINDOW,
      }),
    staleTime: Infinity,
    retry: false,
  });
  const [extra, setExtra] = useState<{ key: string; before: Passage[]; after: Passage[]; error: string | null }>({
    key: "", before: [], after: [], error: null,
  });
  const extraKey = `${doc.id}:${owner ? "owner" : role}:${around}`;
  const before = extra.key === extraKey ? extra.before : [];
  const after = extra.key === extraKey ? extra.after : [];
  const [loadingMore, setLoadingMore] = useState<"before" | "after" | null>(null);

  const data = page.data;
  const firstOffset = data ? data.offset - before.length : 0;
  const lastOffset = data ? data.offset + data.passages.length + after.length - 1 : -1;
  const hasEarlier = data ? firstOffset > 0 : false;
  const hasLater = data ? lastOffset + 1 < data.total : false;

  const extend = useCallback(
    async (direction: "before" | "after") => {
      if (!data || loadingMore) return;
      setLoadingMore(direction);
      const offset = direction === "before" ? Math.max(0, firstOffset - WINDOW) : lastOffset + 1;
      const limit = direction === "before" ? firstOffset - offset : WINDOW;
      try {
        const more = await fetchPassages(doc.id, { role: owner ? undefined : role, offset, limit });
        setExtra((prev) => {
          const base = prev.key === extraKey ? prev : { key: extraKey, before: [], after: [], error: null };
          return direction === "before"
            ? { ...base, key: extraKey, before: [...more.passages, ...base.before], error: null }
            : { ...base, key: extraKey, after: [...base.after, ...more.passages], error: null };
        });
      } catch {
        setExtra((prev) => ({ ...(prev.key === extraKey ? prev : { key: extraKey, before: [], after: [] }), error: "Couldn't load more passages." }));
      } finally {
        setLoadingMore(null);
      }
    },
    [data, loadingMore, firstOffset, lastOffset, doc.id, owner, role, extraKey],
  );

  // bring the cited words into view once, when the window has rendered
  const scrolled = useRef<string | null>(null);
  const targetRef = useCallback(
    (element: HTMLElement | null) => {
      if (!element || scrolled.current === extraKey) return;
      scrolled.current = extraKey;
      element.scrollIntoView({ block: "center" });
    },
    [extraKey],
  );

  const error = page.error instanceof ApiError ? page.error : null;
  if (page.isPending) return <p className="p-5 text-sm text-ink-soft">Loading passages…</p>;
  if (page.isError || !data) {
    return (
      <p role="alert" className="p-5 text-sm text-ink-soft">
        {error?.status === 404
          ? "This document is no longer available."
          : error?.code === "document_not_ready"
          ? error.problem.document_status === "failed"
            ? "Processing failed. This document has no passages."
            : "This document is still being processed. Try again when its status is ready."
          : "Couldn't load the passages."}
      </p>
    );
  }
  const passages = [...before, ...data.passages, ...after];
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      {data.total === 0 && (
        <p className="text-sm text-ink-soft">No passages are visible at this access level.</p>
      )}
      {hasEarlier && (
        <button
          type="button"
          onClick={() => void extend("before")}
          disabled={loadingMore !== null}
          className="mb-4 min-h-9 rounded-[6px] border border-hairline px-3 py-1.5 text-xs text-ink-soft hover:text-ink disabled:opacity-40"
        >
          {loadingMore === "before" ? "Loading…" : `Show earlier passages (${firstOffset} before)`}
        </button>
      )}
      <ol className="flex flex-col gap-4" aria-label="Passages">
        {passages.map((passage) => {
          const isTarget = highlight !== null && passage.chunk_id === highlight.chunkId;
          return (
            <li
              key={passage.chunk_id}
              id={`passage-${passage.chunk_id}`}
              ref={isTarget && !highlight.quotes.length ? targetRef : undefined}
              className={`rounded-[6px] py-1 ${isTarget ? "border-l-2 border-stamp pl-3" : ""}`}
              aria-current={isTarget ? "true" : undefined}
            >
              <p className="font-data mb-1 flex flex-wrap items-center gap-x-2 text-[11px] text-ink-soft">
                <span>{formatPages(passage.pages) ?? `passage ${passage.chunk_index + 1}`}</span>
                {passage.section && <span>· {passage.section}</span>}
                {passage.access_label !== "all" && !owner && (
                  <span className="inline-flex items-center gap-1 rounded border border-hairline px-1 leading-4">
                    <LockIcon className="h-2.5 w-2.5" />
                    {labelName(passage.access_label)}
                  </span>
                )}
                {isTarget && <span className="text-stamp">· cited</span>}
              </p>
              {isTarget ? (
                <HighlightedPassage
                  content={passage.content}
                  quotes={highlight.quotes}
                  markRef={targetRef}
                  className="text-sm leading-6"
                />
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]">{passage.content}</div>
              )}
            </li>
          );
        })}
      </ol>
      {hasLater && (
        <button
          type="button"
          onClick={() => void extend("after")}
          disabled={loadingMore !== null}
          className="mt-4 min-h-9 rounded-[6px] border border-hairline px-3 py-1.5 text-xs text-ink-soft hover:text-ink disabled:opacity-40"
        >
          {loadingMore === "after" ? "Loading…" : `Show later passages (${data.total - lastOffset - 1} after)`}
        </button>
      )}
      {extra.key === extraKey && extra.error && (
        <p role="alert" className="mt-2 text-xs text-error">{extra.error}</p>
      )}
    </div>
  );
}
