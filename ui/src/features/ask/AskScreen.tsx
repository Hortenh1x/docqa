"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCollections, useRole } from "@/app/providers";
import { ACCOUNTS_ENABLED } from "@/lib/api/client";
import { joinNames, labelName, roleName } from "@/lib/access";
import type { QuoteSpan, Source } from "@/lib/api/types";
import { AccessLine } from "./AccessLine";
import { useAsk } from "./AskProvider";
import { AnswerView } from "./AnswerView";
import { CitationReader, type ReaderTarget } from "./CitationReader";
import { Composer } from "./Composer";
import { ErrorPanel } from "./ErrorPanel";
import { MetaLine } from "./MetaLine";
import { QuestionChips } from "./QuestionChips";
import { RefusalPanel } from "./RefusalPanel";
import { SourceDrawer } from "./SourceDrawer";
import { SourceRail } from "./SourceRail";
import { type AskState, type Exchange, isSettled } from "./state";

export function AskScreen() {
  const { selected } = useCollections();
  const { roles, role } = useRole();
  const {
    state, dispatch, ask, viewAs, local, hasEarlier, loadingEarlier, loadEarlier, historyError, clearThread,
  } = useAsk();
  const markTriggerRef = useRef<HTMLElement | null>(null);
  const liveRef = useRef<HTMLDivElement>(null);
  const [reader, setReader] = useState<ReaderTarget | null>(null);

  const thread = state.exchanges.filter((e) => e.collectionId === selected?.id);
  const latest = thread[thread.length - 1] ?? null;

  // screen-reader announcements for the latest exchange: batched (~600ms) while
  // streaming — never per token, a live region updated on every delta would drown
  // the screen reader
  const answerRef = useRef(latest?.answer ?? "");
  answerRef.current = latest?.answer ?? "";
  const phase = latest?.phase ?? "idle";
  useEffect(() => {
    if (!liveRef.current) return;
    if (phase === "streaming") {
      const timer = setInterval(() => {
        if (liveRef.current) liveRef.current.textContent = answerRef.current;
      }, 600);
      return () => clearInterval(timer);
    }
    if (phase === "searching") liveRef.current.textContent = "Searching documents…";
    else if (phase === "done") liveRef.current.textContent = `Answer ready: ${answerRef.current}`;
    else if (phase === "refused")
      liveRef.current.textContent = latest?.access?.hidden_passages
        ? "Not available at your access level."
        : "Not found in the documents.";
    else if (phase === "error") liveRef.current.textContent = "Something went wrong.";
    else liveRef.current.textContent = "";
  }, [phase, latest?.access, latest?.id]);

  // a new question scrolls into view; answers grow below it, the composer stays put
  const lastSubmitted = useRef<string | null>(null);
  useEffect(() => {
    if (!latest || latest.phase !== "searching" || lastSubmitted.current === latest.id) return;
    lastSubmitted.current = latest.id;
    document.getElementById(`exchange-${latest.id}`)?.scrollIntoView({ block: "start" });
  }, [latest]);

  const openSource = useCallback((exchangeId: string, n: number, trigger: HTMLElement | null) => {
    markTriggerRef.current = trigger;
    dispatch({ type: "openSource", exchangeId, n });
  }, [dispatch]);

  const closeSource = useCallback(() => {
    dispatch({ type: "closeSource" });
    markTriggerRef.current?.focus();
  }, [dispatch]);

  // the reader replaces the source panel while it is open (on phones the panel is a
  // modal dialog in the top layer, which would sit above the reader); closing the reader
  // brings the panel back
  const reopenSourceRef = useRef<AskState["activeSource"]>(null);
  const openReader = useCallback((source: Source, quotes: QuoteSpan[]) => {
    reopenSourceRef.current = state.activeSource;
    dispatch({ type: "closeSource" });
    setReader({
      documentId: source.document_id,
      filename: source.filename,
      chunkId: source.chunk_id ?? null,
      chunkIndex: source.chunk_index ?? null,
      pages: source.pages,
      quotes,
    });
  }, [dispatch, state.activeSource]);
  const closeReader = useCallback(() => {
    setReader(null);
    const previous = reopenSourceRef.current;
    reopenSourceRef.current = null;
    if (previous) dispatch({ type: "openSource", ...previous });
    else markTriggerRef.current?.focus();
  }, [dispatch]);

  const activeExchange = state.activeSource
    ? state.exchanges.find((e) => e.id === state.activeSource!.exchangeId) ?? null
    : null;
  const active = activeExchange?.sources.find((s) => s.n === state.activeSource?.n) ?? null;
  const owned = ACCOUNTS_ENABLED && !!selected?.owned;
  const restricted = owned ? [] : selected?.access_labels ?? [];
  const roleMoved = !owned && latest !== null && latest.askedAs !== null && latest.askedAs !== role;

  return (
    // ≥1100px the reading column shifts to make room for the source panel;
    // below that the panel overlays (with a backdrop)
    <div
      className={`flex min-h-[calc(100vh-120px)] flex-col transition-[margin] duration-200 motion-reduce:transition-none ${
        active ? "min-[1100px]:mr-[400px]" : ""
      }`}
    >
      <div ref={liveRef} aria-live="polite" className="visually-hidden" />

      {thread.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 py-16 text-center">
          <h1 className="font-display max-w-full text-4xl tracking-tight [overflow-wrap:anywhere]">
            Ask the documents.
          </h1>
          <QuestionChips questions={selected?.suggested_questions} onPick={ask} />
          {selected && (
            <p role="note" aria-label="Document access" className="max-w-md text-xs leading-5 text-ink-soft">
              {owned ? "Only your account can access these documents. You can search all sections in your private library." : <>
                Viewing as <span className="text-ink">{roleName(role)}</span>. {restricted.length > 0
                  ? <>Some sections here are restricted to {joinNames(restricted.map(labelName))} — switch the role in the top bar to see how the answers change.</>
                  : "This collection has no restricted sections. All roles can access the same documents; use the role menu to explore access levels in other collections."}
              </>}
            </p>
          )}
          {historyError && (
            <p role="alert" className="text-xs text-error">Couldn&apos;t load your earlier questions. {historyError}</p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-8 py-8" aria-label="Conversation">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
            {selected && hasEarlier(selected.id) ? (
              <button
                type="button"
                onClick={() => loadEarlier(selected.id)}
                disabled={loadingEarlier}
                className="min-h-9 rounded-[6px] border border-hairline px-3 py-1.5 text-xs text-ink-soft hover:text-ink disabled:opacity-40"
              >
                {loadingEarlier ? "Loading…" : "Show earlier questions"}
              </button>
            ) : (
              <span className="font-data">
                {thread.length} {thread.length === 1 ? "question" : "questions"}
                {local ? " · kept in this browser" : " · kept in your account"}
              </span>
            )}
            {local && selected && (
              <button
                type="button"
                onClick={() => clearThread(selected.id)}
                className="min-h-9 rounded-[6px] px-2 py-1.5 text-xs text-ink-soft underline-offset-2 hover:text-ink hover:underline"
              >
                Clear history
              </button>
            )}
          </div>
          {historyError && (
            <p role="alert" className="text-xs text-error">Couldn&apos;t load earlier questions. {historyError}</p>
          )}

          {thread.map((exchange) => (
            <ThreadExchange
              key={exchange.id}
              exchange={exchange}
              owned={owned}
              activeN={state.activeSource?.exchangeId === exchange.id ? state.activeSource.n : null}
              onOpenSource={openSource}
              onAsk={ask}
              onViewAs={(next) => viewAs(exchange.question, next)}
              roles={roles}
            />
          ))}
        </div>
      )}

      <div className="sticky bottom-0 mt-auto bg-paper pb-5 pt-2">
        {roleMoved && latest && (
          <div className="mb-2 flex items-center justify-between gap-3 rounded-[6px] border border-hairline bg-sheet px-3 py-1.5 text-xs text-ink-soft">
            <span>
              Role changed to <span className="text-ink">{roleName(role)}</span>.
            </span>
            <button
              type="button"
              onClick={() => ask(latest.question, role)}
              className="rounded-[6px] border border-hairline px-2 py-0.5 text-xs text-ink hover:border-stamp/40"
            >
              Ask again as {roleName(role)}
            </button>
          </div>
        )}
        <Composer disabled={!selected} onSubmit={(q) => ask(q)} />
        {!selected && (
          <p className="mt-2 text-center text-xs text-ink-soft">
            {ACCOUNTS_ENABLED ? "No public collection is currently available. Sign in to use your private library." : "No collection available — set an API key or create a collection first."}
          </p>
        )}
      </div>

      <SourceDrawer
        source={active}
        settled={activeExchange ? isSettled(activeExchange.phase) : false}
        onClose={closeSource}
        onOpenDocument={openReader}
      />
      {reader && <CitationReader target={reader} onClose={closeReader} owner={owned} />}
    </div>
  );
}

function ThreadExchange({
  exchange,
  owned,
  activeN,
  onOpenSource,
  onAsk,
  onViewAs,
  roles,
}: {
  exchange: Exchange;
  owned: boolean;
  activeN: number | null;
  onOpenSource: (exchangeId: string, n: number, trigger: HTMLElement | null) => void;
  onAsk: (question: string) => void;
  onViewAs: (role: string) => void;
  roles: ReturnType<typeof useRole>["roles"];
}) {
  const { selected } = useCollections();
  const open = useCallback(
    (n: number, trigger: HTMLElement | null) => onOpenSource(exchange.id, n, trigger),
    [exchange.id, onOpenSource],
  );
  return (
    <article id={`exchange-${exchange.id}`} className="flex scroll-mt-4 flex-col gap-5" aria-label={exchange.question}>
      <div className="max-w-full self-end rounded-[10px] border border-hairline bg-sheet px-4 py-2.5 text-[15px] shadow-card [overflow-wrap:anywhere]">
        {exchange.question}
      </div>

      {exchange.phase === "searching" && (
        <div aria-hidden="true">
          <p className="mb-2 text-sm text-ink-soft">Searching documents…</p>
          {/* skeletons, not spinners (anti-checklist) */}
          <div className="flex gap-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-16 min-w-44 animate-pulse rounded-[10px] border border-hairline bg-sheet motion-reduce:animate-none"
              />
            ))}
          </div>
        </div>
      )}

      {/* a refusal shows no rail: those passages did not answer the question, and
          next to "not available at your access level" they would read as if they had */}
      {exchange.sources.length > 0 && exchange.phase !== "refused" && (
        <SourceRail
          sources={exchange.sources}
          activeN={activeN}
          folded={exchange.phase === "done"}
          onOpen={open}
        />
      )}

      {!owned && exchange.phase !== "refused" && exchange.phase !== "searching" && (
        <AccessLine access={exchange.access} />
      )}

      {(exchange.phase === "streaming" || exchange.phase === "done") && (
        <AnswerView
          answer={exchange.answer}
          sources={exchange.sources}
          streaming={exchange.phase === "streaming"}
          onOpenSource={open}
        />
      )}

      {exchange.phase === "done" && exchange.done && (
        <MetaLine done={exchange.done} role={owned ? null : exchange.askedAs} />
      )}

      {exchange.phase === "refused" && (
        <RefusalPanel
          question={exchange.question}
          questions={selected?.suggested_questions}
          onPick={onAsk}
          access={owned ? null : exchange.access}
          roles={owned ? [] : roles}
          onViewAs={onViewAs}
        />
      )}

      {exchange.phase === "error" && exchange.error && (
        <ErrorPanel error={exchange.error} onRetry={() => onAsk(exchange.question)} />
      )}
    </article>
  );
}
