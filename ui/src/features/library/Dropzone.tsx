"use client";

import { useRef, useState } from "react";

export function Dropzone({
  onFile,
  busy,
}: {
  onFile: (file: File) => void;
  busy: boolean;
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
        if (file) onFile(file);
      }}
      className={`rounded-[10px] border-[1.5px] border-dashed px-6 py-8 text-center transition-colors ${
        dragOver ? "border-stamp bg-stamp/5" : "border-hairline bg-sheet"
      }`}
    >
      <p className="text-sm text-ink-soft">
        {busy ? "Uploading…" : "Drop PDF, DOCX or MD · up to 25 MB"}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="mt-3 rounded-[6px] border border-hairline bg-paper px-3.5 py-1.5 text-sm disabled:opacity-40"
      >
        Choose a file
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.md,.txt"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
