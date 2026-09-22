import type { AccessInfo, DonePayload, HistoryQuery, QueryOutcome, Source } from "@/lib/api/types";

export type Phase = "idle" | "searching" | "streaming" | "done" | "refused" | "clarification" | "incomplete" | "legacy" | "error";
export interface AskError { message: string; code: string; retryAfterS: number | null; resetAt?: string | null; }

/** Transient rows live here. Settled server rows enter through React Query. */
export interface Exchange {
  id: string; collectionId: string; conversationId: string | null;
  /** Parent captured at submission time. Never derive it from a later completion. */
  parentQueryId: string | null;
  question: string; askedAs: string | null; phase: Phase; queryId: string | null;
  access: AccessInfo | null; sources: Source[]; answer: string; done: DonePayload | null;
  error: AskError | null; createdAt: string; outcome: QueryOutcome | null; contextReset: boolean;
}
export interface ActiveSource { exchangeId: string; n: number; source: Source; }
export interface AskState { exchanges: Exchange[]; activeSource: ActiveSource | null; }
export const initialState: AskState = { exchanges: [], activeSource: null };

export type AskAction =
  | { type: "submit"; exchange: Exchange }
  | { type: "meta"; id: string; queryId: string; access: AccessInfo }
  | { type: "sources"; id: string; sources: Source[] }
  | { type: "delta"; id: string; text: string }
  | { type: "done"; id: string; payload: DonePayload }
  | { type: "error"; id: string; error: AskError }
  | { type: "openSource"; exchangeId: string; source: Source }
  | { type: "closeSource" }
  | { type: "bindConversation"; id: string; conversationId: string }
  | { type: "acknowledge"; exchanges: Array<{ id: string; queryId: string }> }
  | { type: "restore"; exchanges: Exchange[] }
  | { type: "removeConversation"; conversationId: string }
  | { type: "clearCollection"; collectionId: string }
  | { type: "reset" };

export const isSettled = (phase: Phase) => ["done", "refused", "clarification", "incomplete", "legacy", "error"].includes(phase);
export const eligibleParent = (exchange: Pick<Exchange, "queryId" | "outcome">) =>
  exchange.queryId !== null && ["answered", "refused", "clarification"].includes(exchange.outcome ?? "");

function update(state: AskState, id: string, patch: (exchange: Exchange) => Exchange): AskState {
  return { ...state, exchanges: state.exchanges.map((e) => e.id === id ? patch(e) : e) };
}
export function withCitations(sources: Source[], payload: DonePayload): Source[] {
  if (!payload.citations?.length) return sources;
  const byN = new Map(payload.citations.map((c) => [c.n, c]));
  return sources.map((source) => {
    const citation = byN.get(source.n);
    return citation ? { ...source, content: citation.content, quotes: citation.quotes } : source;
  });
}
export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "submit": return { ...state, exchanges: [...state.exchanges, action.exchange] };
    case "meta": return update(state, action.id, (e) => ({ ...e, queryId: action.queryId, access: action.access }));
    case "sources": return update(state, action.id, (e) => ({ ...e, sources: action.sources }));
    case "delta": return update(state, action.id, (e) => ({ ...e, phase: "streaming", answer: e.answer + action.text }));
    case "done": return update(state, action.id, (e) => {
      const outcome = action.payload.outcome ?? (action.payload.refused ? "refused" : "answered");
      const phase: Phase = outcome === "refused" ? "refused" : outcome === "clarification" ? "clarification" : "done";
      return { ...e, phase, outcome, answer: action.payload.answer ?? e.answer, sources: withCitations(e.sources, action.payload), done: action.payload, contextReset: action.payload.context?.reset ?? false };
    });
    case "error": return update(state, action.id, (e) => ({ ...e, phase: "error", outcome: "failed", error: action.error }));
    case "openSource": return { ...state, activeSource: { exchangeId: action.exchangeId, n: action.source.n, source: action.source } };
    case "closeSource": return { ...state, activeSource: null };
    case "bindConversation": return update(state, action.id, (row) => ({ ...row, conversationId: action.conversationId }));
    case "acknowledge": {
      const acknowledged = new Map(action.exchanges.map((row) => [row.id, row.queryId]));
      const activeQueryId = state.activeSource ? acknowledged.get(state.activeSource.exchangeId) : undefined;
      return {
        ...state,
        activeSource: state.activeSource && activeQueryId ? { ...state.activeSource, exchangeId: activeQueryId } : state.activeSource,
        exchanges: state.exchanges.filter((row) => !acknowledged.has(row.id)),
      };
    }
    case "restore": {
      const known = new Set(state.exchanges.map((row) => row.queryId ?? row.id));
      const added = action.exchanges.filter((row) => !known.has(row.queryId ?? row.id));
      return added.length ? { ...state, exchanges: [...state.exchanges, ...added] } : state;
    }
    case "removeConversation": return { ...state, activeSource: state.activeSource && state.exchanges.find((e) => e.id === state.activeSource?.exchangeId)?.conversationId === action.conversationId ? null : state.activeSource, exchanges: state.exchanges.filter((e) => e.conversationId !== action.conversationId) };
    case "clearCollection": return { ...state, activeSource: null, exchanges: state.exchanges.filter((row) => row.collectionId !== action.collectionId) };
    case "reset": return initialState;
  }
}
export function fromHistory(item: HistoryQuery, collectionId: string): Exchange {
  const outcome = item.outcome;
  const phase: Phase = outcome === "refused" ? "refused" : outcome === "clarification" ? "clarification" : outcome === "failed" || outcome === "cancelled" ? "incomplete" : outcome === "legacy_unknown" ? "legacy" : "done";
  return {
    id: item.id, collectionId, conversationId: item.conversation_id, parentQueryId: item.parent_query_id,
    question: item.question, askedAs: item.role, phase, queryId: item.id,
    access: { role: item.role ?? "", hidden_passages: null, hidden_labels: null, hidden_documents: null, hidden_outranking: null, hidden_truncated: null },
    sources: item.sources, answer: item.answer ?? "", outcome, contextReset: item.context_reset,
    done: { answer: item.answer, refused: item.refused, reason: item.reason, confidence: item.confidence, usage: item.usage, latency_ms: item.latency_ms ?? 0, model: item.model, citations: [], outcome, context: { reset: item.context_reset, turns_used: 0 } },
    error: null, createdAt: item.created_at,
  };
}
