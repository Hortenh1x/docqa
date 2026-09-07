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
import { ApiError } from "@/lib/api/client";
import { streamQuery } from "@/lib/api/sse";
import { type AskAction, type AskState, askReducer, initialState, isSettled } from "./state";

const STORAGE_KEY = "docqa.ask";

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
 *  The last settled exchange is also written to sessionStorage, so a reload restores
 *  it; closing the tab forgets it. Switching collections starts fresh. */
export function AskProvider({ children }: { children: React.ReactNode }) {
  const { selected } = useCollections();
  const { role, setRole } = useRole();
  const [state, dispatch] = useReducer(askReducer, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);

  // restore once, after mount (sessionStorage is not available during SSR)
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as AskState;
        if (saved && isSettled(saved.phase)) dispatch({ type: "restore", state: saved });
      }
    } catch {
      /* a private window or blocked storage — nothing to restore */
    }
  }, []);

  // remember settled exchanges; forget the rest
  useEffect(() => {
    try {
      if (isSettled(state.phase)) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      else if (state.phase === "idle") sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, [state]);

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
      dispatch({
        type: "submit",
        question: question.trim(),
        role: asRole,
        collectionId: selected.id,
      });

      streamQuery(
        { collection_id: selected.id, question: question.trim(), role: asRole },
        (event) => {
          if (event.event === "meta")
            dispatch({ type: "meta", queryId: event.data.query_id, access: event.data.access });
          else if (event.event === "sources")
            dispatch({ type: "sources", sources: event.data.sources });
          else if (event.event === "delta") dispatch({ type: "delta", text: event.data.text });
          else if (event.event === "done") dispatch({ type: "done", payload: event.data });
          else if (event.event === "error")
            dispatch({
              type: "error",
              error: { message: event.data.message, code: event.data.code, retryAfterS: null },
            });
        },
        controller.signal,
      ).catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError) {
          dispatch({
            type: "error",
            error: { message: err.message, code: err.code, retryAfterS: err.retryAfterS },
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
      });
    },
    [selected, role],
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
