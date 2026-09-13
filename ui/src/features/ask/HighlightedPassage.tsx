"use client";

import { Fragment } from "react";
import type { QuoteSpan } from "@/lib/api/types";

/** A passage with its pinpoint spans marked in stamp blue. Spans are character offsets
 *  into `content`; overlapping or unordered spans are tolerated. */
export function HighlightedPassage({
  content,
  quotes,
  className = "",
  markRef,
}: {
  content: string;
  quotes: QuoteSpan[];
  className?: string;
  /** receives the first mark — the reader scrolls it into view */
  markRef?: (element: HTMLElement | null) => void;
}) {
  const spans = [...quotes]
    .map((q) => ({ start: Math.max(0, q.start), end: Math.min(content.length, q.end) }))
    .filter((q) => q.end > q.start)
    .sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  spans.forEach((span, index) => {
    const start = Math.max(span.start, cursor);
    if (start >= span.end) return;
    if (start > cursor) parts.push(<Fragment key={`t${index}`}>{content.slice(cursor, start)}</Fragment>);
    parts.push(
      <mark
        key={`m${index}`}
        ref={index === 0 ? markRef : undefined}
        className="rounded-[2px] bg-stamp/20 px-0.5 text-ink box-decoration-clone"
      >
        {content.slice(start, span.end)}
      </mark>,
    );
    cursor = span.end;
  });
  if (cursor < content.length) parts.push(<Fragment key="tail">{content.slice(cursor)}</Fragment>);
  return <div className={`whitespace-pre-wrap [overflow-wrap:anywhere] ${className}`}>{parts}</div>;
}
