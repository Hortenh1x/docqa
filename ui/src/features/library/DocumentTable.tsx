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
    <div className="overflow-x-auto rounded-[10px] border border-hairline bg-sheet shadow-card">
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
            className="rounded-[6px] border border-hairline px-2 py-1 text-xs hover:bg-error/10"
          >
            Retry
          </button>
        </div>
      )}
      {retry.isError && <p role="alert" className="px-4 py-3 text-sm text-error">{errorMessage(retry.error)}</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-xs text-ink-soft">
            <th className="px-4 py-2.5 font-medium">Document</th>
            <th className="px-3 py-2.5 font-medium">Pages</th>
            <th className="px-3 py-2.5 font-medium">Size</th>
            <th className="px-3 py-2.5 font-medium">Status</th>
            <th className="px-3 py-2.5 font-medium">Access</th>
            <th className="px-3 py-2.5 font-medium">Added</th>
            {!readOnly && <th className="px-3 py-2.5" />}
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b border-hairline last:border-0">
              <td className="max-w-64 px-4 py-2.5">
                {owner || canRead(roles, role, doc.access_labels) ? (
                  <button
                    type="button"
                    onClick={() => setReading(doc)}
                    title={`Read ${doc.filename}`}
                    className="font-data block max-w-full truncate text-xs underline-offset-2 hover:text-stamp hover:underline"
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
              <td className="font-data px-3 py-2.5 text-xs text-ink-soft">
                {doc.page_count ?? "—"}
              </td>
              <td className="font-data px-3 py-2.5 text-xs text-ink-soft">
                {formatBytes(doc.size_bytes)}
              </td>
              <td className="px-3 py-2.5">
                <StatusBadge status={doc.status} error={doc.error} />
              </td>
              <td className="px-3 py-2.5">
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
              <td className="font-data px-3 py-2.5 text-xs text-ink-soft">
                {formatDate(doc.created_at)}
              </td>
              {!readOnly && (
                <td className="px-3 py-2.5 text-right">
                  {ACCOUNTS_ENABLED && owner && doc.status === "failed" && <button
                    type="button" onClick={() => retry.mutate(doc.id)} disabled={retry.isPending}
                    aria-label={`Retry processing ${doc.filename}`}
                    className="rounded-[6px] px-2 py-1 text-xs text-stamp hover:bg-stamp/10 disabled:opacity-40"
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
                    className="rounded-[6px] px-2 py-1 text-xs text-ink-soft hover:bg-error/10 hover:text-error disabled:opacity-40"
                  >
                    Delete
                  </button>
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
