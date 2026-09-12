"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { useCollections, useRole } from "@/app/providers";
import { useQueryClient } from "@tanstack/react-query";
import { ACCOUNTS_ENABLED, ApiError, errorMessage, getApiKey } from "@/lib/api/client";
import { streamQuery } from "@/lib/api/sse";
import { type AskAction, type AskState, askReducer, initialState, isSettled } from "./state";

const STORAGE_KEY = "docqa.ask";
const UTC_DAY_MS = 24 * 60 * 60 * 1000;
const nextUTCReset = () => (Math.floor(Date.now() / UTC_DAY_MS) + 1) * UTC_DAY_MS;

interface SavedExchange {
  state: AskState;
  expiresAt: number;
}

interface AskContextValue {
  state: AskState;
  dispatch: (action: AskAction) => void;
  /** ask in the selected collection; `asRole` overrides the current switch (View as …) */
  ask: (question: string, asRole?: string) => void;
  viewAs: (role: string) => void;
}

const AskContext = createContext<AskContextValue | null>(null);

export function useAsk(): AskContextValue {
  const value = useContext(AskContext);
  if (!value) throw new Error("useAsk must be used inside AskProvider");
  return value;
}

/** The conversation lives above the router: leaving for the Library and coming back
 *  finds the answer where it was, and a stream keeps running while you are away.
 *  The last settled exchange is kept until the next UTC midnight; a demo reload
 *  can restore it that day. Keyless reloads and tenant/collection changes start fresh. */
export function AskProvider({
  children,
  restoreSaved,
}: {
  children: React.ReactNode;
  restoreSaved: boolean;
}) {
  const { selected } = useCollections();
  const queryClient = useQueryClient();
  const { role, setRole } = useRole();
  const [state, dispatch] = useReducer(askReducer, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);
  const expiresAtRef = useRef<number | null>(null);

  const expireIfNeeded = useCallback(() => {
    if (expiresAtRef.current === null || Date.now() < expiresAtRef.current) return false;
    expiresAtRef.current = null;
    abortRef.current?.abort();
    dispatch({ type: "reset" });
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* in-memory state must expire even when storage is blocked */
    }
    return true;
  }, []);

  // restore once, after mount (sessionStorage is not available during SSR)
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    // Keyless reloads have no authenticated tenant. A key change always starts fresh.
    if (ACCOUNTS_ENABLED || !restoreSaved || !getApiKey()) return;
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as SavedExchange;
        // Undated legacy entries are deliberately not restored.
        if (
          saved?.state && isSettled(saved.state.phase) &&
          typeof saved.expiresAt === "number" && saved.expiresAt > Date.now() &&
          saved.expiresAt <= nextUTCReset()
        ) {
          expiresAtRef.current = saved.expiresAt;
          dispatch({ type: "restore", state: saved.state });
        }
      }
    } catch {
      /* a private window or blocked storage — nothing to restore */
    }
  }, [restoreSaved]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const checkAtMidnight = () => {
      expireIfNeeded();
      timer = setTimeout(checkAtMidnight, nextUTCReset() - Date.now());
    };
    checkAtMidnight();
    // Suspended tabs can miss timers. Check before the next interaction as well.
    document.addEventListener("visibilitychange", expireIfNeeded);
    document.addEventListener("pointerdown", expireIfNeeded, true);
    document.addEventListener("keydown", expireIfNeeded, true);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", expireIfNeeded);
      document.removeEventListener("pointerdown", expireIfNeeded, true);
      document.removeEventListener("keydown", expireIfNeeded, true);
    };
  }, [expireIfNeeded]);

  // remember settled exchanges; forget the rest
  useEffect(() => {
    if (ACCOUNTS_ENABLED || expireIfNeeded()) return;
    try {
      if (isSettled(state.phase) && expiresAtRef.current !== null) {
        const saved: SavedExchange = { state, expiresAt: expiresAtRef.current };
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
      } else if (state.phase === "idle") sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, [state, expireIfNeeded]);

  // a different collection is a different conversation
  useEffect(() => {
    if (selected && state.collectionId && state.collectionId !== selected.id) {
      abortRef.current?.abort();
      dispatch({ type: "reset" });
    }
  }, [selected, state.collectionId]);

  const ask = useCallback(
    (question: string, asRole: string = role) => {
      if (!selected || !question.trim()) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      expiresAtRef.current = nextUTCReset();
      dispatch({
        type: "submit",
        question: question.trim(),
        role: asRole,
        collectionId: selected.id,
      });

      streamQuery(
        { collection_id: selected.id, question: question.trim(), ...(ACCOUNTS_ENABLED && selected.owned ? {} : { role: asRole }) },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.event === "meta")
            dispatch({ type: "meta", queryId: event.data.query_id, access: event.data.access });
          else if (event.event === "sources")
            dispatch({ type: "sources", sources: event.data.sources });
          else if (event.event === "delta") dispatch({ type: "delta", text: event.data.text });
          else if (event.event === "done") dispatch({ type: "done", payload: event.data });
          else if (event.event === "error")
            dispatch({
              type: "error",
              error: { message: event.data.message, code: event.data.code, retryAfterS: event.data.retry_after_s ?? null, resetAt: event.data.reset_at ?? null },
            });
        },
        controller.signal,
      ).catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError) {
          dispatch({
            type: "error",
            error: { message: errorMessage(err), code: err.code, retryAfterS: err.retryAfterS, resetAt: typeof err.problem.reset_at === "string" ? err.problem.reset_at : null },
          });
        } else {
          dispatch({
            type: "error",
            error: {
              message: "Network error — is the API reachable?",
              code: "network",
              retryAfterS: null,
            },
          });
        }
      }).finally(() => {
        if (ACCOUNTS_ENABLED && !controller.signal.aborted) void queryClient.invalidateQueries({ queryKey: ["budget"] });
      });
    },
    [selected, role, queryClient],
  );

  // "View as Finance" on a refusal: switch the role AND re-ask right away
  const viewAs = useCallback(
    (next: string) => {
      setRole(next);
      ask(state.question, next);
    },
    [ask, setRole, state.question],
  );

  const value = useMemo(() => ({ state, dispatch, ask, viewAs }), [state, ask, viewAs]);
  return <AskContext.Provider value={value}>{children}</AskContext.Provider>;
}
