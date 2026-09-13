import type { AccessInfo, DonePayload, HistoryQuery, Source } from "@/lib/api/types";

export type Phase = "idle" | "searching" | "streaming" | "done" | "refused" | "error";

export interface AskError {
  message: string;
  code: string;
  retryAfterS: number | null;
  resetAt?: string | null;
}

/** One question and everything that came back for it. A thread is the list of
 *  exchanges asked in one collection; the state holds every collection's thread. */
export interface Exchange {
  /** local identity — stable across the stream; `queryId` arrives with `meta` */
  id: string;
  collectionId: string;
  question: string;
  /** the access role the question was asked as (the switch may have moved since) */
  askedAs: string | null;
  phase: Phase;
  queryId: string | null;
  access: AccessInfo | null;
  sources: Source[];
  answer: string;
  done: DonePayload | null;
  error: AskError | null;
  /** ISO timestamp; threads are shown oldest first */
  createdAt: string;
}

export interface AskState {
  /** every collection's exchanges, oldest first */
  exchanges: Exchange[];
  activeSource: { exchangeId: string; n: number } | null;
}

export const initialState: AskState = { exchanges: [], activeSource: null };

export type AskAction =
  | { type: "submit"; exchange: Exchange }
  | { type: "meta"; id: string; queryId: string; access: AccessInfo }
  | { type: "sources"; id: string; sources: Source[] }
  | { type: "delta"; id: string; text: string }
  | { type: "done"; id: string; payload: DonePayload }
  | { type: "error"; id: string; error: AskError }
  | { type: "openSource"; exchangeId: string; n: number }
  | { type: "closeSource" }
  /** merge exchanges from storage or the history API; existing ids win */
  | { type: "restore"; exchanges: Exchange[] }
  | { type: "clearThread"; collectionId: string }
  | { type: "reset" };

/** Terminal phases are worth remembering across navigation and reloads. */
export const isSettled = (phase: Phase) => phase === "done" || phase === "refused" || phase === "error";

function update(state: AskState, id: string, patch: (exchange: Exchange) => Exchange): AskState {
  return {
    ...state,
    exchanges: state.exchanges.map((exchange) => (exchange.id === id ? patch(exchange) : exchange)),
  };
}

/** `done.citations` carries the full passage and the pinpoint spans of every cited block —
 *  fold them into the sources the rail and the panel already show. */
export function withCitations(sources: Source[], payload: DonePayload): Source[] {
  if (!payload.citations?.length) return sources;
  const byN = new Map(payload.citations.map((c) => [c.n, c]));
  return sources.map((source) => {
    const citation = byN.get(source.n);
    return citation ? { ...source, content: citation.content, quotes: citation.quotes } : source;
  });
}

const byTime = (a: Exchange, b: Exchange) =>
  a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0;

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "submit":
      return { ...state, exchanges: [...state.exchanges, action.exchange] };
    case "meta":
      return update(state, action.id, (e) => ({ ...e, queryId: action.queryId, access: action.access }));
    case "sources":
      return update(state, action.id, (e) => ({ ...e, sources: action.sources }));
    case "delta":
      return update(state, action.id, (e) => ({
        ...e,
        phase: "streaming",
        answer: e.answer + action.text,
      }));
    case "done":
      return update(state, action.id, (e) => ({
        ...e,
        phase: action.payload.refused ? "refused" : "done",
        answer: action.payload.answer ?? e.answer,
        sources: withCitations(e.sources, action.payload),
        done: action.payload,
      }));
    case "error":
      return update(state, action.id, (e) => ({ ...e, phase: "error", error: action.error }));
    case "openSource":
      return { ...state, activeSource: { exchangeId: action.exchangeId, n: action.n } };
    case "closeSource":
      return { ...state, activeSource: null };
    case "restore": {
      const known = new Set(state.exchanges.map((e) => e.id));
      const knownQueries = new Set(state.exchanges.map((e) => e.queryId).filter(Boolean));
      const added = action.exchanges.filter(
        (e) => !known.has(e.id) && !(e.queryId && knownQueries.has(e.queryId)),
      );
      if (!added.length) return state;
      return { ...state, exchanges: [...state.exchanges, ...added].sort(byTime) };
    }
    case "clearThread":
      return {
        ...state,
        activeSource: null,
        exchanges: state.exchanges.filter((e) => e.collectionId !== action.collectionId),
      };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

/** A recorded exchange from the history API, in the shape the screen renders. */
export function fromHistory(item: HistoryQuery, collectionId: string): Exchange {
  return {
    id: item.id,
    collectionId,
    question: item.question,
    askedAs: item.role,
    phase: item.refused ? "refused" : "done",
    queryId: item.id,
    // hidden-passage statistics are not recorded; the role is
    access: {
      role: item.role ?? "",
      hidden_passages: null,
      hidden_labels: null,
      hidden_documents: null,
      hidden_outranking: null,
      hidden_truncated: null,
    },
    sources: item.sources,
    answer: item.answer ?? "",
    done: {
      answer: item.answer,
      refused: item.refused,
      reason: item.reason,
      confidence: item.confidence,
      usage: item.usage,
      latency_ms: item.latency_ms ?? 0,
      model: item.model,
    },
    error: null,
    createdAt: item.created_at,
  };
}
