"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { getApiKey, setApiKey } from "@/lib/api/client";
import { useCollections, useRole } from "@/app/providers";
import { Select } from "@/components/Select";
import { PERSONAS, roleName } from "@/lib/access";

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

/** "Viewing as": the demo's access switch. Every question is asked as this role. */
function RoleSwitch() {
  const { roles, role, setRole } = useRole();
  const { selected } = useCollections();
  if (!roles.length) return null;
  const nothingRestricted = !!selected && selected.access_labels.length === 0;
  return (
    <label
      className="flex items-center gap-1.5 text-sm text-ink-soft"
      title={
        nothingRestricted
          ? "This collection has no restricted sections — the role makes no difference here."
          : "Sections restricted to other groups are hidden from this role."
      }
    >
      <span className="hidden sm:inline">Viewing as</span>
      <span className="visually-hidden">Access role</span>
      <Select
        value={role}
        onChange={(e) => setRole(e.target.value)}
        aria-label="Access role"
        className="max-w-44 sm:max-w-60"
      >
        {roles.map((r) => (
          <option key={r.role} value={r.role}>
            {roleName(r.role)}
            {PERSONAS[r.role] ? ` · ${PERSONAS[r.role]}` : ""}
          </option>
        ))}
      </Select>
    </label>
  );
}

export function TopBar() {
  const { collections, selected, selectById } = useCollections();

  return (
    <header className="sticky top-0 z-10 border-b border-hairline bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-[1160px] items-center gap-4 px-4 py-2.5">
        <Link href="/" className="font-display text-lg tracking-tight">
          DocQA
        </Link>

        <label className="flex items-center gap-1.5 text-sm text-ink-soft">
          <span className="visually-hidden">Collection</span>
          <Select
            value={selected?.id ?? ""}
            onChange={(e) => selectById(e.target.value)}
            aria-label="Collection"
            className="max-w-44 sm:max-w-64"
          >
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.read_only ? " · read-only" : ""}
              </option>
            ))}
          </Select>
        </label>

        <RoleSwitch />

        <nav className="flex items-center gap-1" aria-label="Screens">
          <NavLink href="/" label="Ask" />
          <NavLink href="/library" label="Library" />
          <NavLink href="/usage" label="Usage" />
        </nav>

        {/* builds with a baked-in NEXT_PUBLIC_DEMO_API_KEY never ask for a key —
            the field exists only so a keyless build has a way to authenticate */}
        {!process.env.NEXT_PUBLIC_DEMO_API_KEY && (
          <div className="ml-auto">
            <KeyField />
          </div>
        )}
      </div>
    </header>
  );
}
