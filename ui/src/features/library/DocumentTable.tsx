"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { LockIcon } from "@/components/LockIcon";
import { labelName } from "@/lib/access";
import { deleteDocument } from "@/lib/api/client";
import type { DocumentOut } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";
import { DocumentViewer } from "./DocumentViewer";
import { StatusBadge } from "./StatusBadge";

export function DocumentTable({
  documents,
  collectionId,
  readOnly,
}: {
  documents: DocumentOut[];
  collectionId: string;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [reading, setReading] = useState<DocumentOut | null>(null);
  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["documents", collectionId] }),
  });

  if (!documents.length) return null;

  return (
    <div className="overflow-x-auto rounded-[10px] border border-hairline bg-sheet shadow-card">
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
                <button
                  type="button"
                  onClick={() => setReading(doc)}
                  title={`Read ${doc.filename}`}
                  className="font-data block max-w-full truncate text-xs underline-offset-2 hover:text-stamp hover:underline"
                >
                  {doc.filename}
                </button>
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
                {doc.access_labels.length ? (
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
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete ${doc.filename}? Its chunks go with it.`)) {
                        remove.mutate(doc.id);
                      }
                    }}
                    aria-label={`Delete ${doc.filename}`}
                    className="rounded-[6px] px-2 py-1 text-xs text-ink-soft hover:bg-error/10 hover:text-error"
                  >
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {reading && <DocumentViewer doc={reading} onClose={() => setReading(null)} />}
    </div>
  );
}
