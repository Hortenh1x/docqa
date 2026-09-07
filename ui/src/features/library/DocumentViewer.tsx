"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRole } from "@/app/providers";
import { ApiError, fetchDocumentFile } from "@/lib/api/client";
import type { DocumentOut } from "@/lib/api/types";
import { formatBytes } from "@/lib/format";

const TEXT_MIMES = new Set(["text/markdown", "text/plain"]);

/** Full-height reading panel: PDFs render in the browser's viewer, MD/TXT as text. */
export function DocumentViewer({
  doc,
  onClose,
}: {
  doc: DocumentOut;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const { role } = useRole();
  const file = useQuery({
    queryKey: ["document-file", doc.id, role],
    queryFn: () => fetchDocumentFile(doc.id, role),
    staleTime: Infinity,
    retry: false,
  });
  const restricted = file.error instanceof ApiError && file.error.code === "document_restricted";

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
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (file.data && isText) file.data.text().then(setText);
  }, [file.data, isText]);

  useEffect(() => {
    closeRef.current?.focus();

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      // minimal focus trap (same idiom as SourceDrawer)
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        "button, a[href], iframe, [tabindex]:not([tabindex='-1'])",
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
  }, [onClose]);

  const isPdf = doc.mime_type === "application/pdf";

  return (
    <>
      <button
        type="button"
        aria-label="Close reader"
        onClick={onClose}
        className="fixed inset-0 z-20 cursor-default bg-ink/20"
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Read ${doc.filename}`}
        className="fixed bottom-0 right-0 top-0 z-30 flex w-full max-w-[760px] flex-col border-l border-hairline bg-sheet shadow-card max-sm:top-auto max-sm:max-h-[85vh] max-sm:rounded-t-[10px] max-sm:border-t"
      >
        <div className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-data truncate text-sm" title={doc.filename}>
              {doc.filename}
            </h2>
            <p className="font-data mt-0.5 text-[11px] text-ink-soft">
              {doc.page_count ? `${doc.page_count} p. · ` : ""}
              {formatBytes(doc.size_bytes)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {objectUrl && (
              <a
                href={objectUrl}
                download={doc.filename}
                className="rounded-[6px] border border-hairline px-2.5 py-0.5 text-sm text-ink-soft hover:border-stamp/40 hover:text-ink"
              >
                Download
              </a>
            )}
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
        </div>

        {file.isPending && (
          <p className="p-5 text-sm text-ink-soft">Loading the file…</p>
        )}
        {file.isError && restricted && (
          <p role="alert" className="p-5 text-sm text-ink-soft">
            This document holds a section restricted to another group — switch the role in
            the top bar to read it.
          </p>
        )}
        {file.isError && !restricted && (
          <p role="alert" className="p-5 text-sm text-error">
            Couldn&apos;t load the file.
          </p>
        )}

        {isPdf && objectUrl && (
          <iframe title={doc.filename} src={objectUrl} className="min-h-0 w-full flex-1" />
        )}
        {isText && text !== null && (
          <pre className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-5 py-4 font-sans text-sm leading-6">
            {text}
          </pre>
        )}
        {!isPdf && !isText && objectUrl && (
          <p className="p-5 text-sm text-ink-soft">
            This format doesn&apos;t render in the browser — use Download above to read it
            locally.
          </p>
        )}
      </aside>
    </>
  );
}
