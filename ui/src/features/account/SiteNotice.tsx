"use client";

import { useQuery } from "@tanstack/react-query";
import { ACCOUNTS_ENABLED, getSite } from "@/lib/api/client";

export function useSite() {
  return useQuery({ queryKey: ["site"], queryFn: getSite, enabled: ACCOUNTS_ENABLED, staleTime: 300_000 });
}
export function SiteNotice() {
  const site = useSite();
  if (!ACCOUNTS_ENABLED) return null;
  return (
    <aside aria-label="Service notice" className="mx-auto w-full max-w-[760px] border-t border-hairline px-4 py-5 text-xs leading-5 text-ink-soft">
      <p>This service is for exploring document Q&amp;A. Only upload documents you are allowed to share with this service. Do not use it for abusive, unlawful or exploitative purposes.</p>
      {site.data?.operator_contact && <p className="mt-1 break-words">Operator contact: {site.data.operator_contact}</p>}
    </aside>
  );
}
