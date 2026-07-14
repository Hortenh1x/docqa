"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { getApiKey, getUsage, setApiKey } from "@/lib/api/client";
import { formatCost } from "@/lib/format";
import { useCollections } from "@/app/providers";

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      className={`rounded-[6px] px-2.5 py-1 text-sm ${
        active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
      }`}
      aria-current={active ? "page" : undefined}
    >
      {label}
    </Link>
  );
}

function KeyField() {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="text-xs text-ink-soft underline decoration-hairline underline-offset-2 hover:text-ink"
      >
        {getApiKey() ? "change key" : "set API key"}
      </button>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setApiKey(value);
        setEditing(false);
        location.reload(); // simplest way to refetch everything with the new key
      }}
      className="flex items-center gap-1"
    >
      <input
        autoFocus
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="dqa_live_…"
        aria-label="API key (kept in memory only)"
        className="font-data w-44 rounded-[6px] border border-hairline bg-sheet px-2 py-1 text-xs"
      />
      <button type="submit" className="rounded-[6px] bg-stamp px-2 py-1 text-xs text-white">
        use
      </button>
    </form>
  );
}

export function TopBar() {
  const { collections, selected, selectById } = useCollections();
  const usage = useQuery({ queryKey: ["usage"], queryFn: () => getUsage(30), retry: false });

  return (
    <header className="sticky top-0 z-10 border-b border-hairline bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-[1160px] items-center gap-4 px-4 py-2.5">
        <Link href="/" className="font-display text-lg tracking-tight">
          DocQA
        </Link>

        <label className="flex items-center gap-1.5 text-sm text-ink-soft">
          <span className="visually-hidden">Collection</span>
          <select
            value={selected?.id ?? ""}
            onChange={(e) => selectById(e.target.value)}
            aria-label="Collection"
            className="max-w-52 rounded-[6px] border border-hairline bg-sheet px-2 py-1 text-sm text-ink"
          >
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.read_only ? " · read-only" : ""}
              </option>
            ))}
          </select>
        </label>

        <nav className="flex items-center gap-1" aria-label="Screens">
          <NavLink href="/" label="Ask" />
          <NavLink href="/library" label="Library" />
          <NavLink href="/usage" label="Usage" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {usage.data && (
            <span className="font-data hidden text-xs text-ink-soft sm:block">
              {usage.data.queries} queries · {formatCost(usage.data.cost_usd)}
            </span>
          )}
          <KeyField />
        </div>
      </div>
    </header>
  );
}
