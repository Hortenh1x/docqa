"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useCollections } from "@/app/providers";
import { ApiError, listDocuments, uploadDocument } from "@/lib/api/client";
import { Dropzone } from "./Dropzone";
import { DocumentTable } from "./DocumentTable";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
// keep in sync with the backend's DEMO_MAX_FILES_PER_COLLECTION
const DEMO_MAX_FILES = 5;

export function LibraryScreen() {
  const { selected } = useCollections();
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ name: string; fraction: number } | null>(null);

  const documents = useQuery({
    queryKey: ["documents", selected?.id],
    queryFn: () => listDocuments(selected!.id),
    enabled: !!selected,
    // poll every 2s, but ONLY while something is still processing
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.status === "pending" || d.status === "processing")
        ? 2000
        : false,
  });

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

  const fileCount = documents.data?.length ?? 0;

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
            {Math.min(fileCount, DEMO_MAX_FILES)} / {DEMO_MAX_FILES} files
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

      {documents.data && documents.data.length === 0 && !selected.read_only ? (
        <div className="py-14 text-center">
          <p className="font-display text-2xl text-ink-soft">No documents yet.</p>
          <p className="mt-1 text-sm text-ink-soft">Drop a PDF, DOCX or MD above ↑</p>
        </div>
      ) : (
        <DocumentTable
          documents={documents.data ?? []}
          collectionId={selected.id}
          readOnly={selected.read_only}
        />
      )}
    </div>
  );
}
