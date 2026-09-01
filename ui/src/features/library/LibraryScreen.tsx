"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useCollections } from "@/app/providers";
import { ApiError, listDocumentsPage, uploadDocument } from "@/lib/api/client";
import { Dropzone } from "./Dropzone";
import { DocumentTable } from "./DocumentTable";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
// keep in sync with the backend's DEMO_MAX_FILES_PER_COLLECTION
const DEMO_MAX_FILES = 5;
const PAGE_SIZES = [20, 50, 100] as const;

export function LibraryScreen() {
  const { selected } = useCollections();
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ name: string; fraction: number } | null>(null);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  const [page, setPage] = useState(0);

  // a new collection starts from its first page
  useEffect(() => setPage(0), [selected?.id]);

  const documents = useQuery({
    queryKey: ["documents", selected?.id, page, pageSize],
    queryFn: () => listDocumentsPage(selected!.id, pageSize, page * pageSize),
    enabled: !!selected,
    placeholderData: keepPreviousData,
    // poll every 2s, but ONLY while something on this page is still processing
    refetchInterval: (query) =>
      query.state.data?.documents.some(
        (d) => d.status === "pending" || d.status === "processing",
      )
        ? 2000
        : false,
  });

  const total = documents.data?.total ?? 0;
  const pageDocuments = documents.data?.documents ?? [];
  const rangeStart = total === 0 ? 0 : page * pageSize + 1;
  const rangeEnd = page * pageSize + pageDocuments.length;

  // deletions can strand the cursor past the last page — pull it back
  useEffect(() => {
    if (page > 0 && documents.data && page * pageSize >= documents.data.total) {
      setPage(Math.max(0, Math.ceil(documents.data.total / pageSize) - 1));
    }
  }, [documents.data, page, pageSize]);

  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadDocument(selected!.id, file, (fraction) =>
        setProgress({ name: file.name, fraction }),
      ),
    onMutate: (file: File) => {
      setUploadError(null);
      setProgress({ name: file.name, fraction: 0 });
    },
    onSettled: () => setProgress(null),
    onSuccess: () => {
      setPage(0); // the fresh upload sorts first — show it
      queryClient.invalidateQueries({ queryKey: ["documents", selected?.id] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.code === "duplicate_document") {
        setUploadError("This exact file is already in the collection.");
      } else if (err instanceof ApiError) {
        setUploadError(err.message);
      } else {
        setUploadError("Upload failed — network error.");
      }
    },
  });

  if (!selected) {
    return <p className="py-16 text-center text-ink-soft">No collection selected.</p>;
  }

  return (
    <div className="flex flex-col gap-6 py-8">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl tracking-tight">{selected.name}</h1>
          <p className="font-data mt-1 text-xs text-ink-soft">
            {selected.slug} · {selected.embedding_model}
            {selected.read_only ? " · read-only" : ""}
          </p>
        </div>
        {DEMO_MODE && !selected.read_only && (
          <span className="font-data text-xs text-ink-soft" aria-label="Sandbox quota">
            {Math.min(total, DEMO_MAX_FILES)} / {DEMO_MAX_FILES} files
          </span>
        )}
      </div>

      {selected.read_only ? (
        <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 text-sm text-ink-soft">
          Read-only demo collection — uploads are disabled here. Switch to the sandbox
          collection to try your own files.
        </div>
      ) : (
        <Dropzone busy={upload.isPending} progress={progress} onFile={(file) => upload.mutate(file)} />
      )}

      {uploadError && (
        <p role="alert" className="text-sm text-error">
          {uploadError}
        </p>
      )}

      {documents.data && total === 0 && !selected.read_only ? (
        <div className="py-14 text-center">
          <p className="font-display text-2xl text-ink-soft">No documents yet.</p>
          <p className="mt-1 text-sm text-ink-soft">Drop a PDF, DOCX or MD above ↑</p>
        </div>
      ) : (
        <>
          <DocumentTable
            documents={pageDocuments}
            collectionId={selected.id}
            readOnly={selected.read_only}
          />
          {total > PAGE_SIZES[0] && (
            <div className="flex items-center justify-between text-xs text-ink-soft">
              <span className="font-data" aria-live="polite">
                {rangeStart}–{rangeEnd} of {total}
              </span>
              <div className="flex items-center gap-4">
                <div className="font-data flex items-center gap-1" role="group" aria-label="Documents per page">
                  {PAGE_SIZES.map((size) => (
                    <button
                      key={size}
                      type="button"
                      aria-pressed={pageSize === size}
                      onClick={() => {
                        setPageSize(size);
                        setPage(0);
                      }}
                      className={
                        pageSize === size
                          ? "rounded-[6px] border border-hairline bg-sheet px-2 py-0.5 text-ink"
                          : "rounded-[6px] px-2 py-0.5 hover:text-ink"
                      }
                    >
                      {size}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label="Previous page"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    className="rounded-[6px] border border-hairline px-2.5 py-0.5 hover:bg-sheet disabled:opacity-40 disabled:hover:bg-transparent"
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    aria-label="Next page"
                    disabled={rangeEnd >= total}
                    onClick={() => setPage((p) => p + 1)}
                    className="rounded-[6px] border border-hairline px-2.5 py-0.5 hover:bg-sheet disabled:opacity-40 disabled:hover:bg-transparent"
                  >
                    ›
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
