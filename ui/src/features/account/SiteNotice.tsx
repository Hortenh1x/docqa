"use client";

import { useQuery } from "@tanstack/react-query";
import { ACCOUNTS_ENABLED, getSite } from "@/lib/api/client";

export function useSite() {
  return useQuery({ queryKey: ["site"], queryFn: getSite, enabled: ACCOUNTS_ENABLED, staleTime: 300_000 });
}
