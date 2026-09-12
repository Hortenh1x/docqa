"use client";

import { useRef, useState } from "react";

// Match the backend defaults; the API still enforces the configured limit.
const MAX_UPLOAD_MB = process.env.NEXT_PUBLIC_DEMO_MODE === "true" ? 5 : 25;

export function Dropzone({
  onFile,
  busy,
  disabled = false,
  progress,
  maxUploadMb = MAX_UPLOAD_MB,
}: {
  onFile: (file: File) => void;
  busy: boolean;
  disabled?: boolean;
  maxUploadMb?: number;
  progress: { name: string; fraction: number } | null;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file && !busy && !disabled) onFile(file);
      }}
      className={`rounded-[10px] border-[1.5px] border-dashed px-6 py-8 text-center transition-colors ${
        dragOver ? "border-stamp bg-stamp/5" : "border-hairline bg-sheet"
      }`}
    >
      {busy && progress ? (
        <div className="mx-auto max-w-sm text-left">
          <div className="font-data flex justify-between text-xs text-ink-soft">
            <span className="truncate">{progress.name}</span>
            <span>{Math.round(progress.fraction * 100)}%</span>
          </div>
          <div
            role="progressbar"
            aria-valuenow={Math.round(progress.fraction * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Uploading ${progress.name}`}
            className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper"
          >
            <div
              className="h-full rounded-full bg-stamp transition-[width] duration-150"
              style={{ width: `${Math.round(progress.fraction * 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <>
          <p className="text-sm text-ink-soft">Drop PDF, DOCX, MD or TXT · up to {maxUploadMb} MB</p>
          <button
            type="button"
            disabled={busy || disabled}
            onClick={() => inputRef.current?.click()}
            className="mt-3 rounded-[6px] border border-hairline bg-paper px-3.5 py-1.5 text-sm disabled:opacity-40"
          >
            Choose a file
          </button>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        disabled={busy || disabled}
        accept=".pdf,.docx,.md,.txt"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file && !busy && !disabled) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
