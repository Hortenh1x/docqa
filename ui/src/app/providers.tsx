"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { listCollections } from "@/lib/api/client";
import type { Collection } from "@/lib/api/types";

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

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <CollectionProvider>{children}</CollectionProvider>
    </QueryClientProvider>
  );
}
