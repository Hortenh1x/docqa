"use client";

import type { DocumentOut } from "@/lib/api/types";

const STYLES: Record<DocumentOut["status"], { dot: string; text: string; pulse: boolean }> = {
  pending: { dot: "bg-pending", text: "text-pending", pulse: true },
  processing: { dot: "bg-pending", text: "text-pending", pulse: true },
  ready: { dot: "bg-verify", text: "text-verify", pulse: false },
  failed: { dot: "bg-error", text: "text-error", pulse: false },
};

export function StatusBadge({
  status,
  error,
}: {
  status: DocumentOut["status"];
  error: string | null;
}) {
  const style = STYLES[status];
  return (
    <span
      className={`font-data inline-flex items-center gap-1.5 text-xs ${style.text}`}
      title={status === "failed" && error ? error : undefined}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${style.dot} ${
          style.pulse ? "status-pulse" : ""
        }`}
      />
      {status}
    </span>
  );
}
