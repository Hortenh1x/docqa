"use client";

import { useEffect, useRef, useState } from "react";

export function Composer({
  onSubmit,
  disabled,
}: {
  onSubmit: (question: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // "/" focuses the composer from anywhere (unless already typing somewhere)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const grow = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 5 * 24 + 20)}px`;
  };

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSubmit(value);
    setValue("");
    requestAnimationFrame(grow);
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-end gap-2 rounded-[10px] border border-hairline bg-sheet p-2 shadow-card"
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={(e) => {
          setValue(e.target.value);
          grow();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask the documents…  (press / to focus)"
        aria-label="Your question"
        className="max-h-[140px] min-h-[28px] flex-1 resize-none bg-transparent px-2 py-1 outline-none placeholder:text-ink-soft/70"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-[6px] bg-stamp px-3.5 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        Ask
      </button>
    </form>
  );
}
