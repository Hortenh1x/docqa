"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { defaultRangeExtractor, useVirtualizer } from "@tanstack/react-virtual";
import type { Exchange } from "./state";

export function ConversationTranscript({ rows, renderRow, hasEarlier, loadingEarlier, loadEarlier }: {
  rows: Exchange[]; renderRow: (row: Exchange) => React.ReactNode; hasEarlier: boolean;
  loadingEarlier: boolean; loadEarlier: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const pendingAnchor = useRef<{ key: string; top: number } | null>(null);
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  const virtualizer = useVirtualizer({
    count: rows.length, getScrollElement: () => scrollRef.current, estimateSize: () => 280,
    overscan: 6, getItemKey: (index) => rows[index]?.queryId ?? rows[index]?.id ?? index,
    measureElement: (element) => element.getBoundingClientRect().height, useFlushSync: false,
    rangeExtractor: (range) => {
      const base = defaultRangeExtractor(range);
      const focused = focusedKey === null ? -1 : rows.findIndex((row) => String(row.queryId ?? row.id) === focusedKey);
      return focused >= 0 && !base.includes(focused) ? [...base, focused].sort((a, b) => a - b) : base;
    },
  });
  const items = virtualizer.getVirtualItems();
  useEffect(() => {
    if (nearBottom.current && rows.length) virtualizer.scrollToIndex(rows.length - 1, { align: "end" });
  }, [rows, virtualizer]);
  useLayoutEffect(() => {
    const anchor = pendingAnchor.current;
    const viewport = scrollRef.current;
    if (!anchor || !viewport) return;
    const index = rows.findIndex((row) => (row.queryId ?? row.id) === anchor.key);
    if (index < 0) { pendingAnchor.current = null; return; }
    virtualizer.scrollToIndex(index, { align: "start" });
    let attempts = 0;
    const correct = () => {
      const row = viewport.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(anchor.key)}"]`);
      if (row) { viewport.scrollTop += row.getBoundingClientRect().top - viewport.getBoundingClientRect().top - anchor.top; pendingAnchor.current = null; return; }
      if (++attempts < 3) requestAnimationFrame(correct);
    };
    requestAnimationFrame(correct);
  }, [rows, virtualizer]);
  const loadOlder = () => {
    const viewport = scrollRef.current;
    const first = virtualizer.getVirtualItems().find((item) => item.end >= (viewport?.scrollTop ?? 0));
    if (viewport && first) {
      const row = viewport.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(String(first.key))}"]`);
      if (row) pendingAnchor.current = { key: String(first.key), top: row.getBoundingClientRect().top - viewport.getBoundingClientRect().top };
    }
    loadEarlier();
  };
  const jumpToLatest = () => {
    if (!rows.length) return;
    nearBottom.current = true;
    virtualizer.scrollToIndex(rows.length - 1, { align: "end" });
  };
  return <div ref={scrollRef} aria-label="Conversation transcript" tabIndex={0} onFocusCapture={(event) => { setFocusedKey(event.target instanceof HTMLElement ? event.target.closest<HTMLElement>("[data-row-key]")?.dataset.rowKey ?? null : null); }} onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusedKey(null); }} onScroll={(event) => { const node = event.currentTarget; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 64; }} className="max-h-[min(65vh,760px)] overflow-y-auto">
    <div className="sticky top-0 z-10 flex min-h-10 items-center justify-between gap-2 bg-paper py-1">
      <span className="font-data text-xs text-ink-soft">{rows.length} {rows.length === 1 ? "question" : "questions"}</span>
      {hasEarlier && <button type="button" onClick={loadOlder} disabled={loadingEarlier} className="min-h-9 rounded-[6px] border border-hairline px-3 text-xs text-ink-soft hover:text-ink disabled:opacity-40">{loadingEarlier ? "Loading…" : "Show earlier questions"}</button>}
      <button type="button" aria-label="Jump to latest" onClick={jumpToLatest} className="ml-auto min-h-9 rounded-[6px] px-3 text-xs text-ink-soft hover:text-ink">Jump to latest</button>
    </div>
    <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
      {items.map((item) => <div key={item.key} data-index={item.index} data-row-key={item.key} ref={virtualizer.measureElement} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${item.start}px)` }} className="pb-8">{renderRow(rows[item.index])}</div>)}
    </div>
  </div>;
}
