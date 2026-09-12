import type { AccessInfo, DonePayload, Source } from "@/lib/api/types";

export type Phase = "idle" | "searching" | "streaming" | "done" | "refused" | "error";

export interface AskError {
  message: string;
  code: string;
  retryAfterS: number | null;
  resetAt?: string | null;
}

export interface AskState {
  phase: Phase;
  /** the collection the question was asked in — a switch elsewhere resets the screen */
  collectionId: string | null;
  question: string;
  /** the access role the question was asked as (the switch may have moved since) */
  askedAs: string | null;
  queryId: string | null;
  access: AccessInfo | null;
  sources: Source[];
  answer: string;
  done: DonePayload | null;
  error: AskError | null;
  activeSource: number | null;
}

export const initialState: AskState = {
  phase: "idle",
  collectionId: null,
  question: "",
  askedAs: null,
  queryId: null,
  access: null,
  sources: [],
  answer: "",
  done: null,
  error: null,
  activeSource: null,
};

export type AskAction =
  | { type: "submit"; question: string; role: string; collectionId: string }
  | { type: "meta"; queryId: string; access: AccessInfo }
  | { type: "sources"; sources: Source[] }
  | { type: "delta"; text: string }
  | { type: "done"; payload: DonePayload }
  | { type: "error"; error: AskError }
  | { type: "openSource"; n: number }
  | { type: "closeSource" }
  | { type: "restore"; state: AskState }
  | { type: "reset" };

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "submit":
      return {
        ...initialState,
        phase: "searching",
        collectionId: action.collectionId,
        question: action.question,
        askedAs: action.role,
      };
    case "meta":
      return { ...state, queryId: action.queryId, access: action.access };
    case "sources":
      return { ...state, sources: action.sources };
    case "delta":
      return { ...state, phase: "streaming", answer: state.answer + action.text };
    case "done":
      return {
        ...state,
        phase: action.payload.refused ? "refused" : "done",
        answer: action.payload.answer ?? state.answer,
        done: action.payload,
      };
    case "error":
      return { ...state, phase: "error", error: action.error };
    case "openSource":
      return { ...state, activeSource: action.n };
    case "closeSource":
      return { ...state, activeSource: null };
    case "restore":
      return { ...action.state, activeSource: null };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

/** Terminal phases are worth remembering across navigation and reloads. */
export const isSettled = (phase: Phase) => phase === "done" || phase === "refused" || phase === "error";
