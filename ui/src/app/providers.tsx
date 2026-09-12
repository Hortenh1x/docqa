"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useRef } from "react";
import { AskProvider } from "@/features/ask/AskProvider";
import { ACCOUNTS_ENABLED, abortRequests, acceptSession, api, ApiError, fetchSession, onSessionChange, listCollections, listRoles, setApiKey } from "@/lib/api/client";
import { AccountContext, type ProofAction } from "@/features/account/context";
import type { AccountSession, Collection, Role } from "@/lib/api/types";

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });

const ApiKeyContext = createContext<(key: string) => void>(() => {});
export const useChangeApiKey = () => useContext(ApiKeyContext);

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
      const remembered = !ACCOUNTS_ENABLED && sessionStorage.getItem("docqa.collection");
      if (remembered) setSelectedId(remembered);
    }
  }, [selectedId]);

  const value = useMemo<CollectionContextValue>(() => {
    // API order (creation time), with the sandbox pinned to the end: it is the one
    // collection that is "yours to fill", the others are the exhibits
    const collections = [...(data ?? [])].sort(
      (a, b) => Number(a.slug === "sandbox") - Number(b.slug === "sandbox"),
    );
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
        if (!ACCOUNTS_ENABLED) sessionStorage.setItem("docqa.collection", id);
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
      const remembered = !ACCOUNTS_ENABLED && sessionStorage.getItem("docqa.role");
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
        if (!ACCOUNTS_ENABLED) sessionStorage.setItem("docqa.role", next);
      },
    };
  }, [data, roleId]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

function LegacyProviders({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState(() => ({ id: 0, client: createQueryClient() }));
  const changeApiKey = useCallback(
    (key: string) => {
      setApiKey(key); // Abort fetch, SSE and XHR before any new tenant request starts.
      void session.client.cancelQueries();
      session.client.clear();
      try {
        for (const storageKey of ["docqa.ask", "docqa.collection", "docqa.role"]) {
          sessionStorage.removeItem(storageKey);
        }
      } catch {
        /* blocked storage must not prevent changing credentials */
      }
      // Remount tenant state, including route-local readers, drafts and mutations.
      // A fresh client also keeps late mutation callbacks out of the new tenant cache.
      setSession((previous) => ({ id: previous.id + 1, client: createQueryClient() }));
    },
    [session.client],
  );

  return (
    <ApiKeyContext.Provider value={changeApiKey}>
      <QueryClientProvider key={session.id} client={session.client}>
        <CollectionProvider>
          <RoleProvider>
            <AskProvider restoreSaved={session.id === 0}>{children}</AskProvider>
          </RoleProvider>
        </CollectionProvider>
      </QueryClientProvider>
    </ApiKeyContext.Provider>
  );
}


function AccountProviders({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(() => ({ id: 0, client: createQueryClient(), session: null as AccountSession | null, ready: false }));
  const [notice, setNotice] = useState<string | null>(null);
  const [completedProof, setCompletedProof] = useState<ProofAction | null>(null);
  const completedProofRef = useRef<ProofAction | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [revalidating, setRevalidating] = useState(false);
  const current = useRef(state);
  current.current = state;
  const channel = useRef<BroadcastChannel | null>(null);
  const refreshId = useRef(0);

  const beginProof = useCallback(() => {
    completedProofRef.current = null;
    setCompletedProof(null);
    setNotice(null);
  }, []);
  const showingCompletedProof = useCallback(() =>
    completedProofRef.current !== null &&
    window.location.pathname === `/account/${completedProofRef.current}` &&
    !new URLSearchParams(window.location.hash.slice(1)).has("token"), []);

  const clear = useCallback(() => {
    setRevalidating(false);
    abortRequests();
    void current.current.client.cancelQueries();
    current.current.client.clear();
    try {
      for (const key of ["docqa.ask", "docqa.collection", "docqa.role"]) sessionStorage.removeItem(key);
    } catch { /* Storage may be blocked. */ }
    setState(previous => ({ id: previous.id + 1, client: createQueryClient(), session: null, ready: false }));
  }, []);

  const refresh = useCallback(async (preserveAccountForm = false) => {
    const revision = ++refreshId.current;
    const previous = current.current.session;
    const accountRoute = window.location.pathname === "/account" ||
      window.location.pathname.startsWith("/account/");
    // Hide an account form while checking, keeping its one-use proof only in memory.
    // All other routes clear immediately. A changed or invalid session also clears it.
    let preserve = preserveAccountForm && accountRoute && current.current.ready;
    const focused = preserve && document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    if (preserve) {
      abortRequests();
      void current.current.client.cancelQueries();
      setRevalidating(true);
    } else clear();
    setFailure(null);
    try {
      let next: AccountSession;
      try { next = await fetchSession(); }
      catch (error) {
        if (!(error instanceof ApiError) || error.code !== "invalid_session") throw error;
        preserve = false;
        clear();
        if (!showingCompletedProof()) setNotice("Your session expired. Sign in again to access your private documents.");
        // The 401 expired the cookie. This separate request explicitly establishes a guest.
        next = await fetchSession();
      }
      if (revision !== refreshId.current) return;
      const sameIdentity = previous?.user?.id === next.user?.id &&
        previous?.user?.tenant_id === next.user?.tenant_id &&
        previous?.user?.email_verified === next.user?.email_verified;
      if (preserve && sameIdentity) {
        acceptSession(next, { notify: false });
        setState(value => ({ ...value, session: next }));
        setRevalidating(false);
        requestAnimationFrame(() => {
          if (revision === refreshId.current && focused?.isConnected) focused.focus();
        });
      } else acceptSession(next);
    } catch (error) {
      if (revision === refreshId.current && !(error instanceof DOMException && error.name === "AbortError")) {
        setFailure("Could not check your session. Your private content is hidden until the connection is restored.");
      }
    }
  }, [clear, showingCompletedProof]);

  useEffect(() => {
    onSessionChange(next => {
      if (!next) {
        if (!showingCompletedProof()) setNotice("Your session expired. Sign in again to access your private documents.");
        channel.current?.postMessage("changed");
        void refresh();
      } else {
        setRevalidating(false);
        void current.current.client.cancelQueries();
        current.current.client.clear();
        setState(previous => ({ id: previous.id + 1, client: createQueryClient(), session: next, ready: true }));
      }
    });
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel("docqa.account");
      channel.current.onmessage = event => {
        if (event.data === "changing") { ++refreshId.current; clear(); }
        else if (event.data === "changed") void refresh();
      };
    }
    const visible = () => { if (document.visibilityState === "visible") void refresh(true); };
    const restored = (event: PageTransitionEvent) => { if (event.persisted) void refresh(true); };
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("pageshow", restored);
    void refresh();
    return () => {
      ++refreshId.current;
      abortRequests();
      onSessionChange(null);
      channel.current?.close();
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("pageshow", restored);
    };
  }, [clear, refresh, showingCompletedProof]);

  const signedIn = useCallback((next: AccountSession) => {
    ++refreshId.current;
    beginProof();
    acceptSession(next);
    channel.current?.postMessage("changed");
  }, [beginProof]);
  const signOut = useCallback(async () => {
    ++refreshId.current;
    beginProof();
    clear();
    channel.current?.postMessage("changing");
    try {
      await api("/v1/auth/logout", { method: "POST", body: "{}" });
      setNotice("You are signed out. Your private documents remain in your account.");
    } catch (error) {
      if (!(error instanceof ApiError && error.code === "invalid_session")) {
        setNotice("Sign out could not be confirmed. Please try again when your connection is restored.");
      }
    } finally {
      channel.current?.postMessage("changed");
      await refresh();
    }
  }, [beginProof, clear, refresh]);
  const proofCompleted = useCallback(async (action: ProofAction) => {
    // Retain only the confirmed action, never its proof or password. This receipt
    // survives a failed guest bootstrap and its retries outside the cleared tree.
    completedProofRef.current = action;
    setCompletedProof(action);
    setNotice(null);
    channel.current?.postMessage("changing");
    try {
      await refresh();
    } finally {
      channel.current?.postMessage("changed");
    }
  }, [refresh]);

  return (
    <AccountContext.Provider value={{ session: state.session, notice, completedProof, beginProof, signedIn, signOut, proofCompleted }}>
      {(!state.ready || revalidating) && (
        <main className="mx-auto max-w-[760px] px-4 py-16" aria-busy={!failure}>
          <p role={failure ? "alert" : "status"} className="text-sm text-ink-soft">{failure ?? "Checking your session…"}</p>
          {failure && <button type="button" onClick={() => void refresh(true)} className="mt-3 rounded-[6px] border border-hairline px-3 py-2 text-sm">Retry session check</button>}
        </main>
      )}
      {state.ready && <div hidden={revalidating}>
        <QueryClientProvider key={state.id} client={state.client}>
          <CollectionProvider><RoleProvider><AskProvider restoreSaved={false}>
            {notice && <p role="status" className="border-b border-hairline bg-sheet px-4 py-2 text-center text-sm text-ink-soft">{notice}</p>}
            {children}
          </AskProvider></RoleProvider></CollectionProvider>
        </QueryClientProvider>
      </div>}
    </AccountContext.Provider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  return ACCOUNTS_ENABLED ? <AccountProviders>{children}</AccountProviders> : <LegacyProviders>{children}</LegacyProviders>;
}
