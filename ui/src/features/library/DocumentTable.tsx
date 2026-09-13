"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useRole } from "@/app/providers";
import { LockIcon } from "@/components/LockIcon";
import { canRead, joinNames, labelName } from "@/lib/access";
import { ACCOUNTS_ENABLED, ApiError, deleteDocument, reprocessDocument, errorMessage } from "@/lib/api/client";
import type { DocumentOut } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";
import { DocumentViewer } from "./DocumentViewer";
import { StatusBadge } from "./StatusBadge";

function MobileLabel({ children }: { children: React.ReactNode }) {
  return <span aria-hidden="true" className="mb-1 block font-sans text-xs text-ink-soft sm:hidden">{children}</span>;
}

export function DocumentTable({
  documents,
  collectionId,
  readOnly,
  owner = false,
}: {
  documents: DocumentOut[];
  collectionId: string;
  readOnly: boolean;
  owner?: boolean;
}) {
  const queryClient = useQueryClient();
  const { roles, role } = useRole();
  const [reading, setReading] = useState<DocumentOut | null>(null);
  const closeReader = useCallback(() => setReading(null), []);
  const remove = useMutation({
    mutationFn: deleteDocument,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents", collectionId] });
      void queryClient.invalidateQueries({ queryKey: ["ingest-status", collectionId] });
      void queryClient.invalidateQueries({ queryKey: ["storage"] });
    },
  });
  const retry = useMutation({
    mutationFn: reprocessDocument,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["budget"] });
      void queryClient.invalidateQueries({ queryKey: ["documents", collectionId] });
      void queryClient.invalidateQueries({ queryKey: ["ingest-status", collectionId] });
    },
  });
  const failedDocument = remove.isError
    ? documents.find((doc) => doc.id === remove.variables)
    : null;

  if (!documents.length) return null;

  return (
    <div className="relative overflow-x-auto rounded-[10px] border border-hairline bg-sheet shadow-card">
      {failedDocument && (
        <div role="alert" className="flex flex-wrap items-center gap-2 border-b border-hairline px-4 py-3 text-sm text-error">
          <p>
            Couldn&apos;t delete {failedDocument.filename}.{" "}
            {remove.error instanceof ApiError
              ? remove.error.message
              : "Check your connection and try again."}
          </p>
          <button
            type="button"
            onClick={() => remove.mutate(failedDocument.id)}
            aria-label={`Retry delete ${failedDocument.filename}`}
            className="min-h-11 rounded-[6px] border border-hairline px-3 py-2 text-xs hover:bg-error/10 active:bg-error/10"
          >
            Retry
          </button>
        </div>
      )}
      {retry.isError && <p role="alert" className="px-4 py-3 text-sm text-error">{errorMessage(retry.error)}</p>}
      <table role="table" aria-label="Documents" className="block w-full text-sm sm:table">
        <thead role="rowgroup" className="sr-only sm:not-sr-only sm:table-header-group">
          <tr role="row" className="border-b border-hairline text-left text-xs text-ink-soft">
            <th role="columnheader" scope="col" className="px-4 py-2.5 font-medium">Document</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5 font-medium">Pages</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5 font-medium">Size</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5 font-medium">Status</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5 font-medium">Access</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5 font-medium">Added</th>
            {!readOnly && <th role="columnheader" scope="col" className="px-3 py-2.5"><span className="visually-hidden">Actions</span></th>}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block sm:table-row-group">
          {documents.map((doc) => (
            <tr role="row" key={doc.id} className="grid grid-cols-2 border-b border-hairline last:border-0 sm:table-row">
              <td role="cell" className="col-span-2 min-w-0 px-4 py-2.5 sm:max-w-64">
                {owner || canRead(roles, role, doc.access_labels) ? (
                  <button
                    type="button"
                    onClick={() => setReading(doc)}
                    title={`Read ${doc.filename}`}
                    className="font-data block min-h-11 max-w-full text-left text-xs underline-offset-2 hover:text-stamp hover:underline max-sm:break-words sm:truncate"
                  >
                    {doc.filename}
                  </button>
                ) : (
                  <span
                    title={`Restricted to ${joinNames(doc.access_labels.map(labelName))} — switch the role to read it`}
                    className="font-data flex max-w-full items-center gap-1.5 truncate text-xs text-ink-soft"
                  >
                    <LockIcon />
                    {doc.filename}
                  </span>
                )}
                {owner && doc.status === "failed" && doc.error && <p className="mt-1 max-w-64 break-words text-xs leading-5 text-error">{doc.error}</p>}
              </td>
              <td role="cell" className="font-data min-w-0 px-3 py-2.5 text-xs text-ink-soft">
                <MobileLabel>Pages</MobileLabel>
                {doc.page_count ?? "—"}
              </td>
              <td role="cell" className="font-data min-w-0 px-3 py-2.5 text-xs text-ink-soft">
                <MobileLabel>Size</MobileLabel>
                {formatBytes(doc.size_bytes)}
              </td>
              <td role="cell" className="min-w-0 px-3 py-2.5">
                <MobileLabel>Status</MobileLabel>
                <StatusBadge status={doc.status} error={doc.error} />
              </td>
              <td role="cell" className="min-w-0 px-3 py-2.5">
                <MobileLabel>Access</MobileLabel>
                {owner ? <span className="text-xs text-ink-soft">Only you</span> : doc.access_labels.length ? (
                  <span className="flex flex-wrap gap-1">
                    {doc.access_labels.map((label) => (
                      <span
                        key={label}
                        className="font-data inline-flex items-center gap-1 rounded border border-hairline px-1 text-[10px] leading-4 text-ink-soft"
                      >
                        <LockIcon className="h-2.5 w-2.5" />
                        {labelName(label)}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="font-data text-xs text-ink-soft">—</span>
                )}
              </td>
              <td role="cell" className="font-data col-span-2 min-w-0 px-3 py-2.5 text-xs text-ink-soft">
                <MobileLabel>Added</MobileLabel>
                {formatDate(doc.created_at)}
              </td>
              {!readOnly && (
                <td role="cell" className="col-span-2 px-3 py-2.5 text-right">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                  {ACCOUNTS_ENABLED && owner && doc.status === "failed" && <button
                    type="button" onClick={() => retry.mutate(doc.id)} disabled={retry.isPending}
                    aria-label={`Retry processing ${doc.filename}`}
                    className="min-h-11 rounded-[6px] px-3 py-2 text-xs text-stamp hover:bg-stamp/10 enabled:active:bg-stamp/10 disabled:opacity-40"
                  >Retry processing</button>}
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete ${doc.filename}? Its chunks go with it.`)) {
                        remove.mutate(doc.id);
                      }
                    }}
                    aria-label={`Delete ${doc.filename}`}
                    disabled={remove.isPending}
                    className="min-h-11 rounded-[6px] px-3 py-2 text-xs text-ink-soft hover:bg-error/10 hover:text-error enabled:active:bg-error/10 disabled:opacity-40"
                  >
                    Delete
                  </button>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {reading && <DocumentViewer doc={reading} onClose={closeReader} owner={owner} />}
    </div>
  );
}
