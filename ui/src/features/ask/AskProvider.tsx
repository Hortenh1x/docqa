"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCollections, useRole } from "@/app/providers";
import { useAccount } from "@/features/account/context";
import { ACCOUNTS_ENABLED, ApiError, createConversation, errorMessage, listConversationQueries, listConversations, patchConversation } from "@/lib/api/client";
import { streamQuery } from "@/lib/api/sse";
import type { Conversation, ConversationHistoryPage, Source } from "@/lib/api/types";
import { type AskAction, type AskState, type Exchange, askReducer, eligibleParent, fromHistory, initialState } from "./state";

const HISTORY_PAGE = 30;
const LOCAL_STORAGE_KEY = "docqa.ask.v2.demo";
const DEMO_LOCAL_HISTORY = !ACCOUNTS_ENABLED && !!process.env.NEXT_PUBLIC_DEMO_API_KEY;
const newId = () => crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;

interface AskContextValue {
  state: AskState; dispatch: (action: AskAction) => void;
  local: boolean; active: Conversation | null; conversations: Conversation[]; archived: Conversation[];
  selectedConversationId: string | null; selectConversation: (id: string | null) => void;
  newChat: () => Promise<string | null>; rename: (id: string, title: string) => Promise<void>; archive: (archived: boolean) => Promise<void>;
  activeHasMore: boolean; archivedHasMore: boolean; loadingMoreChats: boolean; loadMoreChats: (archived: boolean) => void;
  ask: (question: string, asRole?: string, parentQueryId?: string | null, target?: { collectionId: string; conversationId: string | null }) => void;
  retry: (exchange: Exchange) => void; viewAs: (exchange: Exchange, role: string) => void;
  exchanges: Exchange[]; hasEarlier: boolean; loadingEarlier: boolean; loadEarlier: () => void;
  historyError: string | null; conversationError: string | null; legacyLocal: Exchange[];
  transcriptReady: boolean;
  clearThread: (collectionId: string) => void;
}
const AskContext = createContext<AskContextValue | null>(null);
export const useAsk = () => { const value = useContext(AskContext); if (!value) throw new Error("useAsk must be used inside AskProvider"); return value; };

/** Server conversations are authoritative whenever browser accounts are enabled, for both
 * cookie guests and signed-in accounts. The standalone key/demo build intentionally keeps no
 * shared-key server history. */
export function AskProvider({ children }: { children: React.ReactNode }) {
  const { selected } = useCollections();
  const { role, setRole } = useRole();
  const { session } = useAccount();
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(askReducer, initialState);
  const [selectedByCollection, setSelectedByCollection] = useState<Record<string, string | null>>({});
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [legacyLocal, setLegacyLocal] = useState<Exchange[]>([]);
  const [headReady, setHeadReady] = useState<Record<string, boolean>>({});
  const controllers = useRef(new Set<AbortController>());
  const heads = useRef(new Map<string, string | null>());
  const headSequences = useRef(new Map<string, number>());
  const headEpochs = useRef(new Map<string, number>());
  const completionVersions = useRef(new Map<string, number>());
  const queryIds = useRef(new Map<string, string>());
  const creating = useRef(new Map<string, Promise<Conversation>>());
  const submissions = useRef(0);
  const collectionId = selected?.id ?? null;
  const selectedConversationId = collectionId ? selectedByCollection[collectionId] ?? null : null;
  const identity = session?.user?.id ?? "browser"; // guest scope comes from provider remount, never a CSRF query key
  const remote = ACCOUNTS_ENABLED;

  // This predates server-owned guest conversations. It is a readable browser artifact only,
  // never enters the transcript reducer and can therefore never become parent/context/retry data.
  useEffect(() => {
    if (!remote || session?.user) { setLegacyLocal([]); return; }
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem("docqa.ask.v2.guest") ?? "[]");
      if (!Array.isArray(parsed)) return;
      setLegacyLocal(parsed.filter((item): item is Partial<Exchange> => typeof item === "object" && item !== null && typeof (item as Exchange).question === "string" && typeof (item as Exchange).collectionId === "string").map((item, index) => ({ id: `legacy-local-${index}`, collectionId: item.collectionId!, conversationId: null, parentQueryId: null, question: item.question!, askedAs: item.askedAs ?? null, phase: "legacy", queryId: null, access: null, sources: [], answer: item.answer ?? "", done: null, error: null, createdAt: item.createdAt ?? "", outcome: "legacy_unknown", contextReset: false })));
    } catch { setLegacyLocal([]); }
  }, [remote, session?.user]);

  useEffect(() => {
    if (!DEMO_LOCAL_HISTORY) return;
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(LOCAL_STORAGE_KEY) ?? "[]");
      if (!Array.isArray(parsed)) return;
      const exchanges = parsed.filter((item): item is Exchange => typeof item === "object" && item !== null && typeof (item as Exchange).id === "string" && typeof (item as Exchange).collectionId === "string").map((item) => ({ ...item, conversationId: null, parentQueryId: null, outcome: item.outcome ?? (item.done?.refused ? "refused" : "answered"), contextReset: item.contextReset ?? false }));
      dispatch({ type: "restore", exchanges });
    } catch { /* browser storage is optional */ }
  }, []);
  useEffect(() => {
    if (!DEMO_LOCAL_HISTORY) return;
    try {
      const perCollection = new Map<string, number>(); const kept: Exchange[] = [];
      for (const row of [...state.exchanges].reverse()) {
        if (!["done", "refused", "error", "incomplete", "legacy", "clarification"].includes(row.phase)) continue;
        const count = perCollection.get(row.collectionId) ?? 0;
        if (count >= 30 || kept.length >= 100) continue;
        perCollection.set(row.collectionId, count + 1);
        kept.push({ ...row, access: row.access ? { role: row.access.role, hidden_passages: null, hidden_labels: null, hidden_documents: null, hidden_outranking: null, hidden_truncated: null } : null, sources: row.sources.filter((source) => source.quotes != null) });
      }
      if (kept.length) localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(kept.reverse()));
      else localStorage.removeItem(LOCAL_STORAGE_KEY);
    } catch { /* browser storage is optional */ }
  }, [state.exchanges]);

  const activePage = useInfiniteQuery({
    queryKey: ["conversations", identity, collectionId, "active"],
    queryFn: ({ pageParam }) => listConversations(collectionId!, { archived: "false", limit: 20, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: remote && !!collectionId, staleTime: 15_000, retry: false,
  });
  const archivedPage = useInfiniteQuery({
    queryKey: ["conversations", identity, collectionId, "archived"],
    queryFn: ({ pageParam }) => listConversations(collectionId!, { archived: "true", limit: 20, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: remote && !!collectionId, staleTime: 15_000, retry: false,
  });
  const conversations = useMemo(() => activePage.data?.pages.flatMap((page) => page.conversations) ?? [], [activePage.data]);
  const archived = useMemo(() => archivedPage.data?.pages.flatMap((page) => page.conversations) ?? [], [archivedPage.data]);
  const active = [...conversations, ...archived].find((conversation) => conversation.id === selectedConversationId) ?? null;

  useEffect(() => {
    if (!collectionId || selectedByCollection[collectionId] !== undefined || !conversations.length) return;
    setSelectedByCollection((previous) => ({ ...previous, [collectionId]: conversations[0].id }));
  }, [collectionId, conversations, selectedByCollection]);

  type TranscriptSnapshot = ConversationHistoryPage & { completionVersionAtStart: number };
  const transcript = useInfiniteQuery({
    queryKey: ["transcript", identity, selectedConversationId],
    queryFn: async ({ pageParam }): Promise<TranscriptSnapshot> => {
      const conversationId = selectedConversationId!;
      const completionVersionAtStart = completionVersions.current.get(conversationId) ?? 0;
      const page = await listConversationQueries(conversationId, { limit: HISTORY_PAGE, before: pageParam });
      return { ...page, completionVersionAtStart };
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: remote && !!selectedConversationId, staleTime: 15_000, retry: false,
  });
  const historyRows = useMemo(() => transcript.data?.pages.flatMap((page) => page.queries).map((row) => fromHistory(row, collectionId ?? "")).reverse() ?? [], [collectionId, transcript.data]);
  useLayoutEffect(() => {
    if (!selectedConversationId || !transcript.isSuccess) return;
    const historyIds = new Set(historyRows.map((row) => row.queryId));
    const localCompleted = state.exchanges.filter((row) => row.conversationId === selectedConversationId && eligibleParent(row) && !historyIds.has(row.queryId));
    const serverHead = historyRows.filter(eligibleParent).at(-1) ?? null;
    const localHead = localCompleted.at(-1) ?? null;
    const snapshotVersion = transcript.data?.pages[0]?.completionVersionAtStart ?? -1;
    const currentCompletionVersion = completionVersions.current.get(selectedConversationId) ?? 0;
    // A server page started after the latest local Done is authoritative: successful Done is
    // persisted before it is emitted. An older in-flight page cannot rewind an unacknowledged
    // local completion. Server and browser clocks are never compared for parent authority.
    const newest = snapshotVersion >= currentCompletionVersion ? serverHead ?? localHead : null;
    if (newest && heads.current.get(selectedConversationId) !== newest.queryId) {
      heads.current.set(selectedConversationId, newest.queryId);
      headEpochs.current.set(selectedConversationId, (headEpochs.current.get(selectedConversationId) ?? 0) + 1);
    }
    const acknowledged = state.exchanges
      .filter((row) => row.conversationId === selectedConversationId && row.queryId !== null && historyIds.has(row.queryId))
      .map((row) => ({ id: row.id, queryId: row.queryId! }));
    if (acknowledged.length) dispatch({ type: "acknowledge", exchanges: acknowledged });
    setHeadReady((previous) => previous[selectedConversationId] ? previous : { ...previous, [selectedConversationId]: true });
  }, [historyRows, selectedConversationId, state.exchanges, transcript.isSuccess]);
  const exchanges = useMemo(() => {
    const known = new Set(historyRows.map((row) => row.queryId));
    const local = state.exchanges.filter((row) => remote
      ? row.collectionId === collectionId && row.conversationId === selectedConversationId && (!row.queryId || !known.has(row.queryId))
      : row.collectionId === collectionId);
    return [...historyRows, ...local];
  }, [collectionId, historyRows, remote, state.exchanges, selectedConversationId]);

  useEffect(() => () => { for (const controller of controllers.current) controller.abort(); }, []);
  useEffect(() => {
    if (!remote) return;
    const refreshSettled = () => {
      if (document.visibilityState !== "visible") return;
      void queryClient.invalidateQueries({ queryKey: ["conversations", identity, collectionId] });
      if (selectedConversationId) void queryClient.invalidateQueries({ queryKey: ["transcript", identity, selectedConversationId] });
    };
    document.addEventListener("visibilitychange", refreshSettled);
    return () => document.removeEventListener("visibilitychange", refreshSettled);
  }, [collectionId, identity, queryClient, remote, selectedConversationId]);
  const selectConversation = useCallback((id: string | null) => {
    if (collectionId) setSelectedByCollection((previous) => ({ ...previous, [collectionId]: id }));
  }, [collectionId]);
  const invalidate = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["conversations", identity, collectionId] });
    if (selectedConversationId) await queryClient.invalidateQueries({ queryKey: ["transcript", identity, selectedConversationId] });
  }, [collectionId, identity, queryClient, selectedConversationId]);
  const insertConversation = useCallback((conversation: Conversation) => {
    queryClient.setQueryData<{ pages: Array<{ conversations: Conversation[]; has_more: boolean; next_cursor: string | null }>; pageParams: unknown[] }>(["conversations", identity, conversation.collection_id, conversation.archived ? "archived" : "active"], (old) => old ? { ...old, pages: [{ ...old.pages[0], conversations: old.pages.some((page) => page.conversations.some((row) => row.id === conversation.id)) ? old.pages[0].conversations : [conversation, ...old.pages[0].conversations] }, ...old.pages.slice(1)] } : { pages: [{ conversations: [conversation], has_more: false, next_cursor: null }], pageParams: [undefined] });
  }, [identity, queryClient]);
  const newChat = useCallback(async () => {
    if (!collectionId || !remote) return null;
    setConversationError(null);
    try { const conversation = await createConversation(collectionId); insertConversation(conversation); selectConversation(conversation.id); return conversation.id; }
    catch (error) { setConversationError(errorMessage(error)); return null; }
  }, [collectionId, insertConversation, remote, selectConversation]);
  const rename = useCallback(async (id: string, title: string) => {
    const conversation = [...conversations, ...archived].find((row) => row.id === id);
    if (!conversation || conversation.legacy) return;
    setConversationError(null); try { await patchConversation(id, { title }); await invalidate(); } catch (error) { setConversationError(errorMessage(error)); }
  }, [archived, conversations, invalidate]);
  const archive = useCallback(async (next: boolean) => {
    if (!active || active.legacy) return;
    setConversationError(null); try { await patchConversation(active.id, { archived: next }); await invalidate(); } catch (error) { setConversationError(errorMessage(error)); }
  }, [active, invalidate]);

  const ask = useCallback((question: string, asRole: string = role, requestedParent?: string | null, target?: { collectionId: string; conversationId: string | null }) => {
    if (!collectionId || !question.trim()) return;
    void (async () => {
      const targetCollectionId = target?.collectionId ?? collectionId;
      const capturedConversationId = target ? target.conversationId : selectedConversationId;
      const capturedConversation = capturedConversationId
        ? [...conversations, ...archived].find((conversation) => conversation.id === capturedConversationId)
        : null;
      // Archived and legacy conversations are read-only even if an old rendered callback fires.
      if (remote && capturedConversationId && (!capturedConversation || capturedConversation.archived || capturedConversation.legacy)) return;
      if (remote && capturedConversationId && !headReady[capturedConversationId]) return;
      const parentQueryId = requestedParent === undefined ? (capturedConversationId ? heads.current.get(capturedConversationId) ?? null : null) : requestedParent;
      const sequence = ++submissions.current;
      const capturedEpoch = capturedConversationId ? headEpochs.current.get(capturedConversationId) ?? 0 : 0;
      let conversationId = capturedConversationId;
      const controller = new AbortController(); controllers.current.add(controller);
      const id = newId();
      dispatch({ type: "submit", exchange: { id, collectionId: targetCollectionId, conversationId, parentQueryId, question: question.trim(), askedAs: asRole, phase: "searching", queryId: null, access: null, sources: [], answer: "", done: null, error: null, createdAt: new Date().toISOString(), outcome: null, contextReset: false } });
      if (remote && !conversationId) {
        let pending = creating.current.get(targetCollectionId);
        if (!pending) {
          pending = createConversation(targetCollectionId).finally(() => creating.current.delete(targetCollectionId));
          creating.current.set(targetCollectionId, pending);
        }
        let created: Conversation;
        try { created = await pending; } catch (error) {
          controllers.current.delete(controller);
          dispatch({ type: "error", id, error: { message: errorMessage(error), code: error instanceof ApiError ? error.code : "network_error", retryAfterS: error instanceof ApiError ? error.retryAfterS : null } });
          return;
        }
        conversationId = created.id;
        insertConversation(created);
        dispatch({ type: "bindConversation", id, conversationId });
        // Only a still-empty current selection follows a lazy creation; the callback's
        // captured selection may be stale while a list fetch or route switch settles.
        setSelectedByCollection((previous) => previous[targetCollectionId] == null ? { ...previous, [targetCollectionId]: created.id } : previous);
        await queryClient.invalidateQueries({ queryKey: ["conversations", identity, targetCollectionId] });
      }
      try {
        await streamQuery({ collection_id: targetCollectionId, question: question.trim(), ...(conversationId ? { conversation_id: conversationId, parent_query_id: parentQueryId } : {}), ...(ACCOUNTS_ENABLED && selected?.owned ? {} : { role: asRole }) }, (event) => {
          if (controller.signal.aborted) return;
          if (event.event === "meta") { queryIds.current.set(id, event.data.query_id); dispatch({ type: "meta", id, queryId: event.data.query_id, access: event.data.access }); }
          else if (event.event === "sources") dispatch({ type: "sources", id, sources: event.data.sources });
          else if (event.event === "delta") dispatch({ type: "delta", id, text: event.data.text });
          else if (event.event === "done") {
            dispatch({ type: "done", id, payload: event.data });
            if (conversationId && ["answered", "refused", "clarification"].includes(event.data.outcome) && capturedEpoch === (headEpochs.current.get(conversationId) ?? 0) && sequence >= (headSequences.current.get(conversationId) ?? 0)) {
              // A late older sibling cannot displace a newer submitted head.
              // query_id arrives in meta before terminal done for valid server streams.
              const queryId = queryIds.current.get(id);
              if (queryId) heads.current.set(conversationId, queryId);
              headSequences.current.set(conversationId, sequence);
            }
            if (conversationId && ["answered", "refused", "clarification"].includes(event.data.outcome)) completionVersions.current.set(conversationId, (completionVersions.current.get(conversationId) ?? 0) + 1);
            void queryClient.invalidateQueries({ queryKey: ["transcript", identity, conversationId] });
            void queryClient.invalidateQueries({ queryKey: ["conversations", identity, targetCollectionId] });
          } else if (event.event === "error") {
            dispatch({ type: "error", id, error: { message: event.data.message, code: event.data.code, retryAfterS: event.data.retry_after_s ?? null, resetAt: event.data.reset_at ?? null } });
            if (conversationId) void queryClient.invalidateQueries({ queryKey: ["transcript", identity, conversationId] });
            void queryClient.invalidateQueries({ queryKey: ["conversations", identity, targetCollectionId] });
          }
        }, controller.signal);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) dispatch({ type: "error", id, error: { message: errorMessage(error), code: error instanceof ApiError ? error.code : "network_error", retryAfterS: error instanceof ApiError ? error.retryAfterS : null } });
      } finally { controllers.current.delete(controller); queryIds.current.delete(id); }
    })();
  // state is deliberately not a dependency: it would make send capture a mutable later head.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archived, collectionId, conversations, headReady, identity, insertConversation, queryClient, remote, role, selected?.owned, selectedConversationId, selectConversation]);
  const retry = useCallback((exchange: Exchange) => {
    ask(exchange.question, exchange.askedAs ?? role, exchange.parentQueryId, { collectionId: exchange.collectionId, conversationId: exchange.conversationId });
  }, [ask, role]);
  const viewAs = useCallback((exchange: Exchange, next: string) => {
    setRole(next);
    ask(exchange.question, next, exchange.parentQueryId, { collectionId: exchange.collectionId, conversationId: exchange.conversationId });
  }, [ask, setRole]);

  return <AskContext.Provider value={{ state, dispatch, local: !remote, active, conversations, archived, selectedConversationId, selectConversation, newChat, rename, archive, activeHasMore: !!activePage.hasNextPage, archivedHasMore: !!archivedPage.hasNextPage, loadingMoreChats: activePage.isFetchingNextPage || archivedPage.isFetchingNextPage, loadMoreChats: (archived) => { void (archived ? archivedPage.fetchNextPage() : activePage.fetchNextPage()); }, ask, retry, viewAs, exchanges, hasEarlier: !!transcript.hasNextPage, loadingEarlier: transcript.isFetchingNextPage, loadEarlier: () => { void transcript.fetchNextPage(); }, historyError: activePage.error || transcript.error ? errorMessage(activePage.error ?? transcript.error) : null, conversationError, legacyLocal, transcriptReady: !remote || !selectedConversationId || !!headReady[selectedConversationId], clearThread: (id) => dispatch({ type: "clearCollection", collectionId: id }) }}>{children}</AskContext.Provider>;
}
