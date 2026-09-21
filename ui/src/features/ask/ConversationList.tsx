"use client";

import { useState } from "react";
import type { Conversation } from "@/lib/api/types";

export function ConversationList({
  active, archived, selectedId, onSelect, onNew, onRename, onArchive, activeHasMore, archivedHasMore, loadingMore, loadMore,
}: {
  active: Conversation[]; archived: Conversation[]; selectedId: string | null;
  onSelect: (id: string) => void; onNew: () => void; onRename: (id: string, title: string) => void;
  onArchive: (archived: boolean) => void; activeHasMore: boolean; archivedHasMore: boolean; loadingMore: boolean; loadMore: (archived: boolean) => void;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null);
  const selected = [...active, ...archived].find((chat) => chat.id === selectedId) ?? null;
  const rows = showArchived ? archived : active;
  return <section aria-label="Chats" className="mb-4 border-b border-hairline pb-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-data text-xs text-ink-soft">Chats</span>
      <div className="flex gap-1">
        <button type="button" onClick={() => { setEditing(null); onNew(); }} className="min-h-9 rounded-[6px] border border-hairline px-3 text-xs text-ink hover:border-stamp/40">New chat</button>
        <button type="button" onClick={() => setShowArchived((shown) => !shown)} className="min-h-9 rounded-[6px] px-2 text-xs text-ink-soft hover:text-ink">{showArchived ? "Active" : "Archived"}</button>
      </div>
    </div>
    {selected && <div className="mt-2 flex items-center gap-2">
      {editing?.id === selected.id ? <form className="flex min-w-0 flex-1 gap-1" onSubmit={(event) => { event.preventDefault(); if (editing.title.trim()) onRename(editing.id, editing.title.trim()); setEditing(null); }}>
        <input name="title" aria-label="Chat title" value={editing.title} onChange={(event) => setEditing({ ...editing, title: event.target.value })} maxLength={120} className="min-w-0 flex-1 rounded-[6px] border border-control bg-sheet px-2 py-1 text-sm" autoFocus />
        <button type="submit" className="min-h-8 px-2 text-xs text-stamp">Save</button>
      </form> : <><span className="min-w-0 flex-1 truncate text-sm">{selected.title}</span>{!selected.legacy && <button type="button" onClick={() => setEditing({ id: selected.id, title: selected.title })} className="min-h-8 px-2 text-xs text-ink-soft hover:text-ink">Rename</button>}{!selected.legacy && <button type="button" onClick={() => onArchive(!selected.archived)} className="min-h-8 px-2 text-xs text-ink-soft hover:text-ink">{selected.archived ? "Unarchive" : "Archive"}</button>}</>}
    </div>}
    <ul className="mt-2 flex max-h-32 flex-col overflow-y-auto" aria-label={showArchived ? "Archived chats" : "Active chats"}>
      {rows.map((chat) => <li key={chat.id}><button type="button" onClick={() => { setEditing(null); onSelect(chat.id); }} aria-label={chat.preview ? `${chat.title}. Last question: ${chat.preview.question}` : undefined} aria-current={chat.id === selectedId ? "page" : undefined} className={`min-h-9 w-full rounded-[6px] px-2 py-1 text-left text-sm hover:bg-sheet ${chat.id === selectedId ? "bg-sheet text-ink" : "text-ink-soft"}`}><span className="block truncate">{chat.title}{chat.legacy ? " · Previous questions" : ""}</span>{chat.preview && <span className="block truncate text-xs text-ink-soft">{chat.preview.question}</span>}</button></li>)}
      {!rows.length && <li className="px-2 py-1 text-xs text-ink-soft">{showArchived ? "No archived chats." : "Start a chat when you are ready."}</li>}
    </ul>
    {loadingMore && <p className="mt-1 text-xs text-ink-soft">Loading chats…</p>}
    {!loadingMore && (showArchived ? archivedHasMore : activeHasMore) && <button type="button" onClick={() => loadMore(showArchived)} className="mt-1 min-h-8 text-xs text-ink-soft underline hover:text-ink">Load more chats</button>}
  </section>;
}
