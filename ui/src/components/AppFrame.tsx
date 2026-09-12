"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Providers } from "@/app/providers";
import { SiteNotice } from "@/features/account/SiteNotice";
import { TopBar } from "@/components/TopBar";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function AppFrame({ children }: { children: React.ReactNode }) {
  const publicPage = usePathname() === "/about";
  const content = <main className="mx-auto w-full max-w-[760px] px-4 pb-24">{children}</main>;

  return (
    <>
      {publicPage ? (
        <>
          <header className="border-b border-hairline">
            <nav className="mx-auto flex max-w-[760px] items-center justify-between px-4 py-3" aria-label="Site">
              <Link href="/" className="font-display text-lg tracking-tight">DocQA</Link>
              <Link href="/" className="rounded-[6px] px-2.5 py-1 text-sm text-ink-soft hover:text-ink">Back to Ask</Link>
            </nav>
          </header>
          {content}
        </>
      ) : (
        <Providers>
          {DEMO_MODE && process.env.NEXT_PUBLIC_ACCOUNTS_ENABLED !== "true" && (
            <div className="bg-pending/10 border-b border-pending/30 px-4 py-1.5 text-center text-xs text-ink-soft">
              Public demo — sandbox data is wiped nightly. Policies collections are read-only.
            </div>
          )}
          <TopBar />
          {content}
          <SiteNotice />
        </Providers>
      )}
      <footer className="mx-auto w-full max-w-[760px] border-t border-hairline px-4 py-3 text-xs text-ink-soft">
        <Link href="/about" aria-current={publicPage ? "page" : undefined} className="inline-flex min-h-11 items-center underline decoration-hairline underline-offset-2 hover:text-ink">
          About
        </Link>
      </footer>
    </>
  );
}
