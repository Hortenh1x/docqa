"use client";

import type { SelectHTMLAttributes } from "react";

/** A native select with our own chevron so long option labels get an ellipsis instead of
 *  running underneath the browser's arrow. The wrapper owns the width (pass `w-*` /
 *  `max-w-*` in `className`) and the select fills it — sizing a shrink-to-fit wrapper
 *  from a 100%-wide child is cyclic and collapsed on narrow screens. Native behaviour
 *  (keyboard, mobile pickers, screen readers) is untouched. */
export function Select({
  className = "",
  selectClassName = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { selectClassName?: string }) {
  return (
    <span className={`relative block ${className}`}>
      <select
        {...rest}
        className={`w-full appearance-none truncate rounded-[6px] border border-hairline bg-sheet py-1 pl-2 pr-7 text-sm text-ink ${selectClassName}`}
      >
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 12 12"
        width="12"
        height="12"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-ink-soft"
      >
        <path d="M2.5 4.5 6 8l3.5-3.5" />
      </svg>
    </span>
  );
}
