"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCollections, useRole } from "@/app/providers";
import { useAccount } from "@/features/account/context";
import {
  ACCOUNTS_ENABLED,
  ApiError,
  claimQueries,
  errorMessage,
  listQueries,
} from "@/lib/api/client";
import { streamQuery } from "@/lib/api/sse";
import {
  type AskAction,
  type AskState,
  type Exchange,
  askReducer,
  fromHistory,
  initialState,
  isSettled,
} from "./state";

const STORAGE_PREFIX = "docqa.ask.v2.";
const GUEST_STORAGE_KEY = `${STORAGE_PREFIX}guest`;
/** browser storage holds settled exchanges only, newest kept when the cap is reached */
const PER_COLLECTION_CAP = 30;
const TOTAL_CAP = 100;
const HISTORY_PAGE = 20;

interface AskContextValue {
  state: AskState;
  dispatch: (action: AskAction) => void;
  /** ask in the selected collection; `asRole` overrides the current switch (View as …) */
  ask: (question: string, asRole?: string) => void;
  /** "View as Finance" on a refusal: switch the role AND re-ask right away */
  viewAs: (question: string, role: string) => void;
  /** the thread is kept in this browser (guest / demo) rather than in the account */
  local: boolean;
  /** older exchanges exist in the account's history for this collection */
  hasEarlier: (collectionId: string) => boolean;
  loadingEarlier: boolean;
  loadEarlier: (collectionId: string) => void;
  historyError: string | null;
  clearThread: (collectionId: string) => void;
}

const AskContext = createContext<AskContextValue | null>(null);

export function useAsk(): AskContextValue {
  const value = useContext(AskContext);
  if (!value) throw new Error("useAsk must be used inside AskProvider");
  return value;
}

/** Who the thread belongs to. Guests and the demo build keep it in the browser; a signed-in
 *  account reads it back from the query log; a keyless tab keeps it in memory only (the key
 *  is not persisted, so nothing tied to it may be). */
function threadIdentity(userId: string | undefined): {
  storageKey: string | null;
  remote: boolean;
} {
  if (ACCOUNTS_ENABLED) {
    return userId
      ? { storageKey: null, remote: true }
      : { storageKey: GUEST_STORAGE_KEY, remote: false };
  }
  return {
    storageKey: process.env.NEXT_PUBLIC_DEMO_API_KEY ? `${STORAGE_PREFIX}demo` : null,
    remote: false,
  };
}

function readStored(key: string): Exchange[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is Exchange =>
        typeof e === "object" && e !== null && typeof (e as Exchange).id === "string" &&
        typeof (e as Exchange).collectionId === "string" && isSettled((e as Exchange).phase),
    );
  } catch {
    return []; // a private window, blocked storage or a stale shape — start fresh
  }
}

/** Settled exchanges only, cited sources only (the folded rail is what a restored answer
 *  shows anyway), newest kept when the caps bite. */
function storable(exchanges: Exchange[]): Exchange[] {
  const perCollection = new Map<string, number>();
  const kept: Exchange[] = [];
  for (const exchange of [...exchanges].reverse()) {
    if (!isSettled(exchange.phase)) continue;
    const seen = perCollection.get(exchange.collectionId) ?? 0;
    if (seen >= PER_COLLECTION_CAP || kept.length >= TOTAL_CAP) continue;
    perCollection.set(exchange.collectionId, seen + 1);
    kept.push({
      ...exchange,
      sources: exchange.sources.filter((s) => s.quotes != null),
      error: exchange.phase === "error" ? exchange.error : null,
    });
  }
  return kept.reverse();
}

function writeStored(key: string, exchanges: Exchange[]) {
  try {
    if (!exchanges.length) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(exchanges));
  } catch {
    // quota or blocked storage: keep the newest half and try once more, then give up
    try {
      localStorage.setItem(key, JSON.stringify(exchanges.slice(-Math.ceil(exchanges.length / 2))));
    } catch {
      /* the in-memory thread still works for this tab */
    }
  }
}

const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

/** The conversation lives above the router: leaving for the Library and coming back finds
 *  every answer where it was, and a stream keeps running while you are away. Each
 *  collection has its own thread; switching collections switches threads and forgets
 *  nothing. Guests keep their threads in this browser, accounts in their query history. */
export function AskProvider({ children }: { children: React.ReactNode }) {
  const { selected } = useCollections();
  const queryClient = useQueryClient();
  const { role, setRole } = useRole();
  const { session } = useAccount();
  const userId = session?.user?.id;
  const { storageKey, remote } = useMemo(() => threadIdentity(userId), [userId]);
  const [state, dispatch] = useReducer(askReducer, initialState);
  const controllers = useRef(new Set<AbortController>());
  const restoredRef = useRef<string | null>(null);
  const storedSignature = useRef("");
  const [earlier, setEarlier] = useState<Record<string, boolean>>({});
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // restore this identity's threads once, after mount (storage is not available during SSR)
  useEffect(() => {
    if (!storageKey || restoredRef.current === storageKey) return;
    restoredRef.current = storageKey;
    const stored = readStored(storageKey);
    if (stored.length) dispatch({ type: "restore", exchanges: stored });
  }, [storageKey]);

  // remember settled exchanges; skip the work while a stream only adds tokens
  useEffect(() => {
    if (!storageKey || restoredRef.current !== storageKey) return;
    const signature = state.exchanges
      .filter((e) => isSettled(e.phase))
      .map((e) => `${e.id}:${e.phase}`)
      .join("|");
    if (signature === storedSignature.current) return;
    storedSignature.current = signature;
    writeStored(storageKey, storable(state.exchanges));
  }, [state.exchanges, storageKey]);

  // signed in: the questions this browser asked as a guest follow the account
  useEffect(() => {
    if (!remote) return;
    const guest = readStored(GUEST_STORAGE_KEY);
    if (!guest.length) return;
    const ids = guest.map((e) => e.queryId).filter((id): id is string => !!id);
    if (!ids.length) {
      writeStored(GUEST_STORAGE_KEY, []);
      return;
    }
    let cancelled = false;
    claimQueries(ids)
      .then(() => {
        if (cancelled) return;
        writeStored(GUEST_STORAGE_KEY, []);
        void queryClient.invalidateQueries({ queryKey: ["history"] });
      })
      .catch(() => {
        /* offline or signed out again — the guest store stays for the next sign-in */
      });
    return () => {
      cancelled = true;
    };
  }, [remote, queryClient]);

  // accounts: the selected collection's thread comes from the query log
  const history = useQuery({
    queryKey: ["history", userId, selected?.id],
    queryFn: () => listQueries(selected!.id, { limit: HISTORY_PAGE }),
    enabled: remote && !!selected,
    staleTime: Infinity,
    retry: false,
  });
  const historyPage = history.data;
  useEffect(() => {
    if (!historyPage || !selected) return;
    dispatch({
      type: "restore",
      exchanges: historyPage.queries.map((q) => fromHistory(q, selected.id)),
    });
    setEarlier((prev) =>
      prev[selected.id] === historyPage.has_more ? prev : { ...prev, [selected.id]: historyPage.has_more },
    );
  }, [historyPage, selected]);
  useEffect(() => {
    setHistoryError(history.error ? errorMessage(history.error) : null);
  }, [history.error]);

  useEffect(() => {
    const active = controllers.current;
    return () => {
      for (const controller of active) controller.abort();
    };
  }, []);

  const ask = useCallback(
    (question: string, asRole: string = role) => {
      if (!selected || !question.trim()) return;
      const controller = new AbortController();
      controllers.current.add(controller);
      const id = newId();
      const collectionId = selected.id;
      dispatch({
        type: "submit",
        exchange: {
          id,
          collectionId,
          question: question.trim(),
          askedAs: asRole,
          phase: "searching",
          queryId: null,
          access: null,
          sources: [],
          answer: "",
          done: null,
          error: null,
          createdAt: new Date().toISOString(),
        },
      });

      streamQuery(
        { collection_id: collectionId, question: question.trim(), ...(ACCOUNTS_ENABLED && selected.owned ? {} : { role: asRole }) },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.event === "meta")
            dispatch({ type: "meta", id, queryId: event.data.query_id, access: event.data.access });
          else if (event.event === "sources")
            dispatch({ type: "sources", id, sources: event.data.sources });
          else if (event.event === "delta") dispatch({ type: "delta", id, text: event.data.text });
          else if (event.event === "done") dispatch({ type: "done", id, payload: event.data });
          else if (event.event === "error")
            dispatch({
              type: "error",
              id,
              error: { message: event.data.message, code: event.data.code, retryAfterS: event.data.retry_after_s ?? null, resetAt: event.data.reset_at ?? null },
            });
        },
        controller.signal,
      ).catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError) {
          dispatch({
            type: "error",
            id,
            error: { message: errorMessage(err), code: err.code, retryAfterS: err.retryAfterS, resetAt: typeof err.problem.reset_at === "string" ? err.problem.reset_at : null },
          });
        } else {
          dispatch({
            type: "error",
            id,
            error: {
              message: "Network error — is the API reachable?",
              code: "network",
              retryAfterS: null,
            },
          });
        }
      }).finally(() => {
        controllers.current.delete(controller);
        if (ACCOUNTS_ENABLED && !controller.signal.aborted) void queryClient.invalidateQueries({ queryKey: ["budget"] });
      });
    },
    [selected, role, queryClient],
  );

  const viewAs = useCallback(
    (question: string, next: string) => {
      setRole(next);
      ask(question, next);
    },
    [ask, setRole],
  );

  const exchangesRef = useRef(state.exchanges);
  exchangesRef.current = state.exchanges;
  const loadEarlier = useCallback(
    (collectionId: string) => {
      if (!remote || loadingEarlier) return;
      const oldest = exchangesRef.current.find((e) => e.collectionId === collectionId && e.queryId);
      if (!oldest?.queryId) return;
      setLoadingEarlier(true);
      setHistoryError(null);
      listQueries(collectionId, { limit: HISTORY_PAGE, before: oldest.queryId })
        .then((page) => {
          dispatch({
            type: "restore",
            exchanges: page.queries.map((q) => fromHistory(q, collectionId)),
          });
          setEarlier((prev) => ({ ...prev, [collectionId]: page.has_more }));
        })
        .catch((err: unknown) => setHistoryError(errorMessage(err)))
        .finally(() => setLoadingEarlier(false));
    },
    [remote, loadingEarlier],
  );

  const clearThread = useCallback((collectionId: string) => {
    dispatch({ type: "clearThread", collectionId });
  }, []);

  const hasEarlier = useCallback((collectionId: string) => earlier[collectionId] === true, [earlier]);

  const value = useMemo(
    () => ({
      state,
      dispatch,
      ask,
      viewAs,
      local: !remote,
      hasEarlier,
      loadingEarlier,
      loadEarlier,
      historyError,
      clearThread,
    }),
    [state, ask, viewAs, remote, hasEarlier, loadingEarlier, loadEarlier, historyError, clearThread],
  );
  return <AskContext.Provider value={value}>{children}</AskContext.Provider>;
}
