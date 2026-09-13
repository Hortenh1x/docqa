"use client";

import { useQuery } from "@tanstack/react-query";
import { DocumentViewer } from "@/features/library/DocumentViewer";
import { getDocument } from "@/lib/api/client";
import type { DocumentOut, QuoteSpan } from "@/lib/api/types";

/** What the source panel hands to the reader: the document, the cited chunk, the words. */
export interface ReaderTarget {
  documentId: string;
  filename: string;
  chunkId: number | null;
  chunkIndex: number | null;
  pages: [number, number] | null;
  quotes: QuoteSpan[];
}

/** The document reader opened from a citation: passages view, centred on the cited
 *  chunk with the quoted words marked. The document's metadata (format, size) loads in
 *  the background — the passages need none of it. */
export function CitationReader({
  target,
  onClose,
  owner,
}: {
  target: ReaderTarget;
  onClose: () => void;
  owner: boolean;
}) {
  const document = useQuery({
    queryKey: ["document", target.documentId],
    queryFn: () => getDocument(target.documentId),
    staleTime: Infinity,
    retry: false,
  });
  const provisional: DocumentOut = {
    id: target.documentId,
    collection_id: "",
    filename: target.filename,
    mime_type: "application/octet-stream",
    size_bytes: 0,
    sha256: "",
    status: "ready",
    error: null,
    page_count: null,
    created_at: "",
    processed_at: null,
    access_labels: [],
  };
  return (
    <DocumentViewer
      doc={document.data ?? provisional}
      onClose={onClose}
      owner={owner}
      initialMode="passages"
      highlight={{
        chunkId: target.chunkId,
        chunkIndex: target.chunkIndex,
        pages: target.pages,
        quotes: target.quotes,
      }}
    />
  );
}
