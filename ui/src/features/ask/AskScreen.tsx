"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCollections, useRole } from "@/app/providers";
import { ACCOUNTS_ENABLED } from "@/lib/api/client";
import type { QuoteSpan, Source } from "@/lib/api/types";
import { AccessLine } from "./AccessLine";
import { useAsk } from "./AskProvider";
import { AnswerView } from "./AnswerView";
import { CitationReader, type ReaderTarget } from "./CitationReader";
import { ClarificationPanel } from "./ClarificationPanel";
import { Composer } from "./Composer";
import { ConversationList } from "./ConversationList";
import { ConversationTranscript } from "./ConversationTranscript";
import { ErrorPanel } from "./ErrorPanel";
import { MetaLine } from "./MetaLine";
import { QuestionChips } from "./QuestionChips";
import { RefusalPanel } from "./RefusalPanel";
import { SourceDrawer } from "./SourceDrawer";
import { SourceRail } from "./SourceRail";
import type { Exchange } from "./state";

export function AskScreen() {
  const { selected } = useCollections(); const { roles } = useRole();
  const askState = useAsk();
  const { state, dispatch, ask, retry, viewAs, active, conversations, archived, selectedConversationId, selectConversation, newChat, rename, archive, activeHasMore, archivedHasMore, loadingMoreChats, loadMoreChats, exchanges, hasEarlier, loadingEarlier, loadEarlier, historyError, conversationError, legacyLocal, transcriptReady, clearThread } = askState;
  const [reader, setReader] = useState<ReaderTarget | null>(null);
  const trigger = useRef<HTMLElement | null>(null); const live = useRef<HTMLDivElement>(null);
  const reopenSource = useRef<typeof state.activeSource>(null);
  const [focusAfterNewChat, setFocusAfterNewChat] = useState<string | null>(null);
  const latest = exchanges[exchanges.length - 1] ?? null;
  const owned = ACCOUNTS_ENABLED && !!selected?.owned;
  const restricted = selected?.access_labels.filter((label) => label !== "all") ?? [];
  const accessNote = selected && (owned || restricted.length > 0) ? (
    <p role="note" aria-label="Document access" className="max-w-md text-xs leading-5 text-ink-soft">
      {owned
        ? "Only your account can access these documents."
        : "Switch demo roles to explore restricted sections."}
    </p>
  ) : null;
  // A selected collection may have no named chat yet. The first submission lazily creates one.
  const composerDisabled = !selected || (ACCOUNTS_ENABLED && selectedConversationId !== null && (!active || active.archived || active.legacy || !transcriptReady));
  const readOnly = !!active && (active.archived || active.legacy);
  const activeSource = state.activeSource?.source ?? null;

  useEffect(() => {
    if (!live.current) return;
    if (latest?.phase === "searching") live.current.textContent = "Searching documents…";
    else if (latest?.phase === "clarification") live.current.textContent = `Clarification needed: ${latest.answer}`;
    else if (latest?.phase === "done") live.current.textContent = `Answer ready: ${latest.answer}`;
    else if (latest?.phase === "refused") live.current.textContent = "Not found in the documents.";
    else if (latest?.phase === "error") live.current.textContent = "Something went wrong.";
  }, [latest?.answer, latest?.id, latest?.phase]);
  const openSource = useCallback((exchangeId: string, source: Source, opener: HTMLElement | null) => { trigger.current = opener; dispatch({ type: "openSource", exchangeId, source }); }, [dispatch]);
  const closeSource = useCallback(() => { dispatch({ type: "closeSource" }); if (trigger.current?.isConnected) trigger.current.focus(); else document.querySelector<HTMLElement>("[aria-label='Jump to latest']")?.focus(); }, [dispatch]);
  const openReader = useCallback((source: Source, quotes: QuoteSpan[]) => { reopenSource.current = state.activeSource; dispatch({ type: "closeSource" }); setReader({ documentId: source.document_id, filename: source.filename, chunkId: source.chunk_id ?? null, chunkIndex: source.chunk_index ?? null, pages: source.pages, quotes }); }, [dispatch, state.activeSource]);
  const closeReader = useCallback(() => { setReader(null); const previous = reopenSource.current; reopenSource.current = null; if (previous) dispatch({ type: "openSource", exchangeId: previous.exchangeId, source: previous.source }); else trigger.current?.focus(); }, [dispatch]);
  const startNewChat = useCallback(async () => {
    const conversationId = await newChat();
    if (conversationId) setFocusAfterNewChat(conversationId);
  }, [newChat]);
  useEffect(() => {
    if (!focusAfterNewChat) return;
    if (selectedConversationId !== focusAfterNewChat) { setFocusAfterNewChat(null); return; }
    if (composerDisabled || !transcriptReady) return;
    const frame = requestAnimationFrame(() => {
      const composer = document.querySelector<HTMLTextAreaElement>("textarea[aria-label='Your question']");
      if (composer && !composer.disabled) { composer.focus(); setFocusAfterNewChat(null); }
    });
    return () => cancelAnimationFrame(frame);
  }, [composerDisabled, focusAfterNewChat, selectedConversationId, transcriptReady]);

  return <div data-source-open={activeSource ? "true" : undefined} className="reading-column flex min-h-[calc(100vh-120px)] flex-col transition-[margin] duration-200 motion-reduce:transition-none">
    <div ref={live} aria-live="polite" className="visually-hidden" />
    {ACCOUNTS_ENABLED && selected && <ConversationList active={conversations} archived={archived} selectedId={selectedConversationId} onSelect={selectConversation} onNew={() => void startNewChat()} onRename={(id, title) => void rename(id, title)} onArchive={(next) => void archive(next)} activeHasMore={activeHasMore} archivedHasMore={archivedHasMore} loadingMore={loadingMoreChats} loadMore={loadMoreChats} />}
    {!selected ? <Empty title="Ask the documents." description={ACCOUNTS_ENABLED ? "No public collection is currently available. Sign in to use your private library." : "No collection available — set an API key or create a collection first."} />
      : ACCOUNTS_ENABLED && !active && exchanges.length === 0 ? (
        <Empty title="Ask the documents." description="Start a named chat when you are ready." action={() => void startNewChat()}>
          <QuestionChips questions={selected.suggested_questions} onPick={ask} />
          {accessNote}
        </Empty>
      ) : exchanges.length === 0 ? (
        <Empty title="Ask the documents.">
          <QuestionChips questions={selected.suggested_questions} onPick={ask} />
          {accessNote}
        </Empty>
      )
      : <ConversationTranscript key={selectedConversationId ?? selected.id} rows={exchanges} hasEarlier={hasEarlier} loadingEarlier={loadingEarlier} loadEarlier={loadEarlier} renderRow={(exchange) => <ThreadExchange key={exchange.id} exchange={exchange} owned={owned} readOnly={readOnly} activeN={state.activeSource?.exchangeId === exchange.id ? state.activeSource.n : null} onOpenSource={openSource} onAsk={ask} onRetry={retry} onViewAs={(next) => viewAs(exchange, next)} roles={roles} />} />}
    {historyError && <p role="alert" className="mt-2 text-xs text-error">Couldn&apos;t load this chat. {historyError}</p>}
    {conversationError && <p role="alert" className="mt-2 text-xs text-error">Couldn&apos;t update this chat. {conversationError}</p>}
    {ACCOUNTS_ENABLED && !owned && legacyLocal.filter((row) => row.collectionId === selected?.id).length > 0 && <details className="mt-3 rounded-[6px] border border-hairline bg-sheet px-3 py-2 text-sm"><summary className="min-h-9 cursor-pointer py-1 text-ink-soft">Earlier local history</summary><div className="flex flex-col gap-3 pt-2">{legacyLocal.filter((row) => row.collectionId === selected?.id).map((row) => <div key={row.id} className="border-t border-hairline pt-2"><p className="font-medium">{row.question}</p>{row.answer && <p className="mt-1 whitespace-pre-wrap text-ink-soft">{row.answer}</p>}</div>)}</div></details>}
    {active?.archived && <p className="mt-3 flex items-center justify-between gap-3 rounded-[6px] border border-hairline bg-sheet px-3 py-2 text-sm text-ink-soft">This chat is archived.<button type="button" onClick={() => void startNewChat()} className="min-h-9 rounded-[6px] border border-hairline px-3 text-xs text-ink hover:border-stamp/40">Continue in new chat</button></p>}
    {active?.legacy && <p className="mt-3 text-sm text-ink-soft">Previous questions are read-only.</p>}
    {!ACCOUNTS_ENABLED && selected && exchanges.length > 0 && <button type="button" onClick={() => clearThread(selected.id)} className="mt-2 min-h-9 self-start text-xs text-ink-soft underline hover:text-ink">Clear history</button>}
    <div className="sticky bottom-0 mt-auto bg-paper pb-5 pt-2"><Composer disabled={composerDisabled} onSubmit={(question) => ask(question)} /></div>
    <SourceDrawer source={activeSource} settled={!!state.activeSource && exchanges.some((row) => row.id === state.activeSource?.exchangeId && row.phase !== "streaming")} onClose={closeSource} onOpenDocument={openReader} />
    {reader && <CitationReader target={reader} onClose={closeReader} owner={owned} />}
  </div>;
}

function Empty({ title, description, action, children }: { title: string; description?: string; action?: () => void; children?: React.ReactNode }) {
  return <div className="flex flex-1 flex-col items-center justify-center gap-5 py-16 text-center"><h1 className="font-display max-w-full text-4xl tracking-tight [overflow-wrap:anywhere]">{title}</h1>{description && <p className="max-w-md text-sm text-ink-soft">{description}</p>}{action && <button type="button" onClick={action} className="min-h-11 rounded-[6px] border border-hairline px-4 text-sm text-ink hover:border-stamp/40">New chat</button>}{children}</div>;
}

function ThreadExchange({ exchange, owned, readOnly, activeN, onOpenSource, onAsk, onRetry, onViewAs, roles }: { exchange: Exchange; owned: boolean; readOnly: boolean; activeN: number | null; onOpenSource: (id: string, source: Source, opener: HTMLElement | null) => void; onAsk: (question: string) => void; onRetry: (exchange: Exchange) => void; onViewAs: (role: string) => void; roles: ReturnType<typeof useRole>["roles"] }) {
  const { selected } = useCollections(); const open = useCallback((n: number, opener: HTMLElement | null) => { const source = exchange.sources.find((item) => item.n === n); if (source) onOpenSource(exchange.id, source, opener); }, [exchange, onOpenSource]);
  const regularAnswer = exchange.phase === "streaming" || exchange.phase === "done";
  return <article id={`exchange-${exchange.id}`} className="flex scroll-mt-4 flex-col gap-5" aria-label={exchange.question}>
    <div className="max-w-full self-end rounded-[10px] border border-hairline bg-sheet px-4 py-2.5 text-[15px] shadow-card [overflow-wrap:anywhere]">{exchange.question}</div>
    {exchange.phase === "searching" && <p className="text-sm text-ink-soft">Searching documents…</p>}
    {exchange.contextReset && <p role="note" className="text-xs text-ink-soft">This answer starts with fresh context.</p>}
    {exchange.sources.length > 0 && !["refused", "clarification", "legacy", "incomplete"].includes(exchange.phase) && <SourceRail sources={exchange.sources} activeN={activeN} folded={exchange.phase === "done"} onOpen={open} />}
    {!owned && !["refused", "searching", "clarification", "legacy"].includes(exchange.phase) && <AccessLine access={exchange.access} />}
    {regularAnswer && <AnswerView answer={exchange.answer} sources={exchange.sources} streaming={exchange.phase === "streaming"} onOpenSource={open} />}
    {exchange.phase === "clarification" && <ClarificationPanel question={exchange.answer} />}
    {exchange.phase === "refused" && <RefusalPanel question={exchange.question} questions={readOnly ? undefined : selected?.suggested_questions} onPick={onAsk} access={owned ? null : exchange.access} roles={owned ? [] : roles} onViewAs={readOnly ? undefined : onViewAs} />}
    {exchange.phase === "incomplete" && <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4"><p className="font-data text-xs text-ink-soft">Incomplete</p>{exchange.answer && <p className="mt-2 whitespace-pre-wrap text-[15px] leading-7">{exchange.answer}</p>}{!readOnly && <button type="button" onClick={() => onRetry(exchange)} className="mt-3 min-h-9 rounded-[6px] border border-hairline px-3 text-sm text-ink hover:border-stamp/40">Retry</button>}</div>}
    {exchange.phase === "legacy" && <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4"><p className="font-data text-xs text-ink-soft">Historical answer</p>{exchange.answer && <p className="mt-2 whitespace-pre-wrap text-[15px] leading-7">{exchange.answer}</p>}</div>}
    {exchange.phase === "error" && exchange.answer && <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4"><p className="font-data text-xs text-ink-soft">Partial answer</p><p className="mt-2 whitespace-pre-wrap text-[15px] leading-7">{exchange.answer}</p></div>}
    {exchange.phase === "error" && exchange.error && (readOnly ? <div className="rounded-[10px] border border-error/40 bg-error/10 px-5 py-4"><p className="font-medium text-ink">Something went wrong</p><p className="mt-1 text-sm text-ink-soft">{exchange.error.message}</p></div> : <ErrorPanel error={exchange.error} onRetry={() => onRetry(exchange)} />)}
    {regularAnswer && exchange.done && <MetaLine done={exchange.done} role={owned ? null : exchange.askedAs} />}
  </article>;
}
