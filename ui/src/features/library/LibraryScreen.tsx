"use client";

import Link from "next/link";
import { useAccount } from "@/features/account/context";
import { useSite } from "@/features/account/SiteNotice";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useCollections } from "@/app/providers";
import { LockIcon } from "@/components/LockIcon";
import { labelName } from "@/lib/access";
import { ACCOUNTS_ENABLED, api, errorMessage, ApiError, getIngestStatus, listDocumentsPage, uploadDocument } from "@/lib/api/client";
import type { IngestStatus, StorageUsage } from "@/lib/api/types";
import { formatBytes, formatCost, formatTokens } from "@/lib/format";
import { Dropzone } from "./Dropzone";
import { DocumentTable } from "./DocumentTable";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
// keep in sync with the backend's DEMO_MAX_FILES_PER_COLLECTION
const DEMO_MAX_FILES = 5;
const PAGE_SIZES = [20, 50, 100] as const;

export function LibraryScreen() {
  const { selected } = useCollections();
  const queryClient = useQueryClient();
  const { session } = useAccount();
  const site = useSite();
  const writable = ACCOUNTS_ENABLED ? selected?.writable === true : !selected?.read_only;
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ name: string; fraction: number } | null>(null);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  const [page, setPage] = useState(0);

  const storage = useQuery({
    queryKey: ["storage", session?.user?.id],
    queryFn: () => api<StorageUsage>("/v1/storage"),
    enabled: ACCOUNTS_ENABLED && !!session?.user && !!selected?.owned,
    retry: false,
  });

  // a new collection starts from its first page
  useEffect(() => setPage(0), [selected?.id]);

  const documents = useQuery({
    queryKey: ["documents", selected?.id, page, pageSize],
    queryFn: () => listDocumentsPage(selected!.id, pageSize, page * pageSize),
    enabled: !!selected,
    placeholderData: ACCOUNTS_ENABLED ? undefined : keepPreviousData,
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

  const questionWaitPolls = useRef(0);
  const ingest = useQuery({
    queryKey: ["ingest-status", selected?.id],
    queryFn: () => getIngestStatus(selected!.id),
    enabled: !!selected,
    refetchInterval: (query) => {
      const status = query.state.data;
      if (!status) return false;
      if (status.pending + status.processing > 0) {
        questionWaitPolls.current = 0;
        return 2000;
      }
      // settled, questions still cooking (one LLM call) — keep polling for ~2 min max
      if (status.ready > 0 && !status.suggested_questions && questionWaitPolls.current < 40) {
        questionWaitPolls.current += 1;
        return 3000;
      }
      return false;
    },
  });

  useEffect(() => {
    if (ACCOUNTS_ENABLED && ingest.dataUpdatedAt) {
      void queryClient.invalidateQueries({ queryKey: ["budget"] });
    }
  }, [ingest.dataUpdatedAt, queryClient]);

  // fresh questions → refresh the collections list so the Ask screen's chips pick them up
  const questionsKey = JSON.stringify(ingest.data?.suggested_questions ?? null);
  const prevQuestionsKey = useRef(questionsKey);
  useEffect(() => {
    if (prevQuestionsKey.current !== questionsKey) {
      prevQuestionsKey.current = questionsKey;
      queryClient.invalidateQueries({ queryKey: ["collections"] });
    }
  }, [questionsKey, queryClient]);

  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadDocument(selected!.id, file, (fraction) =>
        setProgress({ name: file.name, fraction }),
      ),
    onMutate: (file: File) => {
      setUploadError(null);
      setProgress({ name: file.name, fraction: 0 });
    },
    onSettled: () => {
      setProgress(null);
      if (ACCOUNTS_ENABLED) {
        void queryClient.invalidateQueries({ queryKey: ["budget"] });
        void queryClient.invalidateQueries({ queryKey: ["storage"] });
      }
    },
    onSuccess: () => {
      setPage(0); // the fresh upload sorts first — show it
      queryClient.invalidateQueries({ queryKey: ["documents", selected?.id] });
      queryClient.invalidateQueries({ queryKey: ["ingest-status", selected?.id] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.code === "duplicate_document") {
        setUploadError("This exact file is already in the collection.");
      } else if (err instanceof ApiError) {
        setUploadError(errorMessage(err));
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
            {ACCOUNTS_ENABLED ? (selected.owned ? "Private library · only your account" : "Public demo · read-only") : `${selected.slug} · ${selected.embedding_model}${selected.read_only ? " · read-only" : ""}`}
          </p>
          {selected.access_labels.length > 0 && !selected.owned && (
            <p className="font-data mt-1 flex items-center gap-1.5 text-xs text-ink-soft">
              <LockIcon />
              restricted sections: {selected.access_labels.map(labelName).join(", ")}
            </p>
          )}
        </div>
        {DEMO_MODE && !ACCOUNTS_ENABLED && !selected.read_only && (
          <span className="font-data text-xs text-ink-soft" aria-label="Sandbox quota">
            {Math.min(total, DEMO_MAX_FILES)} / {DEMO_MAX_FILES} files
          </span>
        )}
      </div>

      {ACCOUNTS_ENABLED && selected.owned && session?.user && (
        <section aria-label="Document storage" className="text-sm leading-6 text-ink-soft">
          {storage.isError ? <p role="alert">Could not load storage usage. <button type="button" className="text-stamp underline" onClick={() => void storage.refetch()}>Retry</button></p>
            : storage.data ? <>
              <p className="font-data text-xs text-ink">{formatBytes(storage.data.used_bytes)} of {formatBytes(storage.data.limit_bytes)} used · {formatBytes(storage.data.remaining_bytes)} remaining</p>
              <p>Any number of files, within your account’s total storage limit. Deleting a document frees space.</p>
              {storage.data.remaining_bytes === 0 && <p role="status" className="text-error">Storage full. Delete a document to make room for another upload.</p>}
            </> : <p role="status">Loading storage usage…</p>}
        </section>
      )}

      {ACCOUNTS_ENABLED ? (
        writable ? <>
          <div className="text-sm leading-6 text-ink-soft">
            <p>{site.data?.document_privacy ?? "Your documents belong to your private account."} Personal and confidential documents are allowed.</p>
            {site.data ? <><p>Before you upload, these providers process your content:</p><ul className="mt-1 list-disc pl-5">{site.data.providers.map(provider => <li key={provider.name}><span className="text-ink">{provider.name}</span>: {provider.receives}</li>)}</ul></> : <p role="status">{site.isError ? "Provider information is unavailable. Retry after the connection is restored." : "Loading provider information…"}</p>}
            <p className="mt-2">Your originals stay in your account until you delete them, including when processing fails.</p>
          </div>
          {site.data && <Dropzone busy={upload.isPending} disabled={storage.data?.remaining_bytes === 0} progress={progress} maxUploadMb={site.data.upload_max_mb} onFile={file => upload.mutate(file)} />}
        </> : <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 text-sm leading-6 text-ink-soft">
          {selected.owned ? <><p>Verify your email before uploading to your private library.</p>{session?.registration_available ? <Link href="/account/resend" className="text-stamp underline">Resend verification email</Link> : <p>Verification email delivery is currently unavailable.</p>}</> : <><p>Public demo collection. Anyone can explore these documents; uploads and changes are disabled here.</p>{session?.user ? <p>Choose My documents in the collection menu to use your private library.</p> : <Link href="/account" className="text-stamp underline">Sign in to upload private documents</Link>}</>}
        </div>
      ) : selected.read_only ? (
        <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 text-sm text-ink-soft">
          Read-only demo collection — uploads are disabled here. Switch to the sandbox
          collection to try your own files.
        </div>
      ) : (
        <Dropzone busy={upload.isPending} progress={progress} onFile={(file) => upload.mutate(file)} />
      )}

      {ingest.data && <IngestProgress status={ingest.data} owner={!!selected.owned} />}

      {uploadError && (
        <p role="alert" className="text-sm text-error">
          {uploadError}
        </p>
      )}

      {documents.data && total === 0 && writable ? (
        <div className="py-14 text-center">
          <p className="font-display text-2xl text-ink-soft">No documents yet.</p>
          <p className="mt-1 text-sm text-ink-soft">Drop a PDF, DOCX or MD above ↑</p>
        </div>
      ) : (
        <>
          <DocumentTable
            documents={pageDocuments}
            collectionId={selected.id}
            readOnly={!writable}
            owner={ACCOUNTS_ENABLED && !!selected.owned}
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

/** One quiet line under the dropzone: ETA + running tokens/cost while ingesting,
 *  "generating questions" while the LLM drafts them, a cost summary when idle. */
function IngestProgress({ status, owner }: { status: IngestStatus; owner: boolean }) {
  const inFlight = status.pending + status.processing;
  if (inFlight > 0) {
    return (
      <p role="status" className="font-data text-xs text-ink-soft">
        Processing {inFlight} {inFlight === 1 ? "document" : "documents"}…
        {status.eta_seconds !== null && ` ~${status.eta_seconds}s left`}
        {" · "}
        {formatTokens(status.embedded_tokens)} tokens embedded
        {status.embedding_cost_usd !== null && ` · ${formatCost(status.embedding_cost_usd)}`}
      </p>
    );
  }
  if (status.ready > 0 && !status.suggested_questions) {
    return (
      <p role="status" className="font-data text-xs text-ink-soft">
        Generating suggested questions…
      </p>
    );
  }
  if (status.ready > 0) {
    const restricted = Object.entries(status.access.chunks_by_label).filter(
      ([label]) => label !== "all",
    );
    return (
      <p className="font-data text-xs text-ink-soft">
        {formatTokens(status.embedded_tokens)} tokens embedded
        {status.embedding_cost_usd !== null &&
          ` · ${formatCost(status.embedding_cost_usd)} embedding cost`}
        {!owner && status.access.restricted_chunks > 0 &&
          ` · ${status.access.restricted_chunks} restricted ${
            status.access.restricted_chunks === 1 ? "passage" : "passages"
          } (${restricted.map(([label, n]) => `${labelName(label)} ${n}`).join(" · ")})`}
      </p>
    );
  }
  return null;
}
