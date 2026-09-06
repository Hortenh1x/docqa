"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { listCollections, listRoles } from "@/lib/api/client";
import type { Collection, Role } from "@/lib/api/types";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

interface CollectionContextValue {
  collections: Collection[];
  selected: Collection | null;
  selectById: (id: string) => void;
  loadError: string | null;
}

const CollectionContext = createContext<CollectionContextValue>({
  collections: [],
  selected: null,
  selectById: () => {},
  loadError: null,
});

export const useCollections = () => useContext(CollectionContext);

function CollectionProvider({ children }: { children: React.ReactNode }) {
  const { data, error } = useQuery({ queryKey: ["collections"], queryFn: listCollections });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (selectedId === null) {
      const remembered = sessionStorage.getItem("docqa.collection");
      if (remembered) setSelectedId(remembered);
    }
  }, [selectedId]);

  const value = useMemo<CollectionContextValue>(() => {
    const collections = data ?? [];
    const selected =
      collections.find((c) => c.id === selectedId) ??
      collections.find((c) => c.slug === "policies-en") ??
      collections[0] ??
      null;
    return {
      collections,
      selected,
      selectById: (id: string) => {
        setSelectedId(id);
        sessionStorage.setItem("docqa.collection", id);
      },
      loadError: error ? String(error) : null,
    };
  }, [data, selectedId, error]);

  return <CollectionContext.Provider value={value}>{children}</CollectionContext.Provider>;
}

interface RoleContextValue {
  /** roles the API accepts, in privilege order (empty until loaded) */
  roles: Role[];
  /** the role every question is asked as */
  role: string;
  setRole: (role: string) => void;
}

const RoleContext = createContext<RoleContextValue>({
  roles: [],
  role: "employee",
  setRole: () => {},
});

export const useRole = () => useContext(RoleContext);

/** The demo's "who is asking" switch. Remembered per tab like the collection; the
 *  default is whatever the API marks as default (least privilege). */
function RoleProvider({ children }: { children: React.ReactNode }) {
  const { data } = useQuery({ queryKey: ["roles"], queryFn: listRoles, staleTime: Infinity });
  const [roleId, setRoleId] = useState<string | null>(null);

  useEffect(() => {
    if (roleId === null) {
      const remembered = sessionStorage.getItem("docqa.role");
      if (remembered) setRoleId(remembered);
    }
  }, [roleId]);

  const value = useMemo<RoleContextValue>(() => {
    const roles = data ?? [];
    const fallback = roles.find((r) => r.default)?.role ?? roles[0]?.role ?? "employee";
    const role = roleId && roles.some((r) => r.role === roleId) ? roleId : fallback;
    return {
      roles,
      role,
      setRole: (next: string) => {
        setRoleId(next);
        sessionStorage.setItem("docqa.role", next);
      },
    };
  }, [data, roleId]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <CollectionProvider>
        <RoleProvider>{children}</RoleProvider>
      </CollectionProvider>
    </QueryClientProvider>
  );
}
