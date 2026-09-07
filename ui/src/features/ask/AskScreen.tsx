"use client";

import { useCallback, useEffect, useRef } from "react";
import { useCollections, useRole } from "@/app/providers";
import { joinNames, labelName, roleName } from "@/lib/access";
import { AccessLine } from "./AccessLine";
import { useAsk } from "./AskProvider";
import { AnswerView } from "./AnswerView";
import { Composer } from "./Composer";
import { ErrorPanel } from "./ErrorPanel";
import { MetaLine } from "./MetaLine";
import { QuestionChips } from "./QuestionChips";
import { RefusalPanel } from "./RefusalPanel";
import { SourceDrawer } from "./SourceDrawer";
import { SourceRail } from "./SourceRail";

export function AskScreen() {
  const { selected } = useCollections();
  const { roles, role } = useRole();
  const { state, dispatch, ask, viewAs } = useAsk();
  const markTriggerRef = useRef<HTMLElement | null>(null);
  const liveRef = useRef<HTMLDivElement>(null);

  // screen-reader announcements: batched (~600ms) while streaming — never per token,
  // a live region updated on every delta would drown the screen reader
  const answerRef = useRef(state.answer);
  answerRef.current = state.answer;
  useEffect(() => {
    if (!liveRef.current) return;
    if (state.phase === "streaming") {
      const timer = setInterval(() => {
        if (liveRef.current) liveRef.current.textContent = answerRef.current;
      }, 600);
      return () => clearInterval(timer);
    }
    if (state.phase === "searching") liveRef.current.textContent = "Searching documents…";
    else if (state.phase === "done") liveRef.current.textContent = `Answer ready: ${state.answer}`;
    else if (state.phase === "refused")
      liveRef.current.textContent = state.access?.hidden_passages
        ? "Not available at your access level."
        : "Not found in the documents.";
    else if (state.phase === "error") liveRef.current.textContent = "Something went wrong.";
  }, [state.phase, state.answer, state.access]);

  const openSource = useCallback((n: number, trigger: HTMLElement | null) => {
    markTriggerRef.current = trigger;
    dispatch({ type: "openSource", n });
  }, []);

  const closeSource = useCallback(() => {
    dispatch({ type: "closeSource" });
    markTriggerRef.current?.focus();
  }, []);

  const active = state.sources.find((s) => s.n === state.activeSource) ?? null;
  const restricted = selected?.access_labels ?? [];
  const roleMoved = state.phase !== "idle" && state.askedAs !== null && state.askedAs !== role;

  return (
    // ≥1100px the reading column shifts to make room for the source panel;
    // below that the panel overlays (with a backdrop)
    <div
      className={`flex min-h-[calc(100vh-120px)] flex-col transition-[margin] duration-200 ${
        active ? "min-[1100px]:mr-[400px]" : ""
      }`}
    >
      <div ref={liveRef} aria-live="polite" className="visually-hidden" />

      {state.phase === "idle" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 py-16 text-center">
          <h1 className="font-display text-4xl tracking-tight">Ask the documents.</h1>
          <QuestionChips questions={selected?.suggested_questions} onPick={ask} />
          {restricted.length > 0 && (
            <p className="max-w-md text-xs leading-5 text-ink-soft">
              Viewing as <span className="text-ink">{roleName(role)}</span>. Some sections
              here are restricted to {joinNames(restricted.map(labelName))} — switch the
              role in the top bar to see how the answers change.
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-5 py-8">
          <div className="self-end rounded-[10px] border border-hairline bg-sheet px-4 py-2.5 text-[15px] shadow-card">
            {state.question}
          </div>

          {state.phase === "searching" && (
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
          {state.sources.length > 0 && state.phase !== "refused" && (
            <SourceRail
              sources={state.sources}
              activeN={state.activeSource}
              onOpen={openSource}
            />
          )}

          {state.phase !== "refused" && state.phase !== "searching" && (
            <AccessLine access={state.access} />
          )}

          {(state.phase === "streaming" || state.phase === "done") && (
            <AnswerView
              answer={state.answer}
              sources={state.sources}
              streaming={state.phase === "streaming"}
              onOpenSource={openSource}
            />
          )}

          {state.phase === "done" && state.done && (
            <MetaLine done={state.done} role={state.askedAs} />
          )}

          {state.phase === "refused" && (
            <RefusalPanel
              question={state.question}
              questions={selected?.suggested_questions}
              onPick={ask}
              access={state.access}
              roles={roles}
              onViewAs={viewAs}
            />
          )}

          {state.phase === "error" && state.error && (
            <ErrorPanel error={state.error} onRetry={() => ask(state.question)} />
          )}
        </div>
      )}

      <div className="sticky bottom-0 mt-auto bg-paper pb-5 pt-2">
        {roleMoved && (
          <div className="mb-2 flex items-center justify-between gap-3 rounded-[6px] border border-hairline bg-sheet px-3 py-1.5 text-xs text-ink-soft">
            <span>
              Role changed to <span className="text-ink">{roleName(role)}</span>.
            </span>
            <button
              type="button"
              onClick={() => ask(state.question, role)}
              className="rounded-[6px] border border-hairline px-2 py-0.5 text-xs text-ink hover:border-stamp/40"
            >
              Ask again as {roleName(role)}
            </button>
          </div>
        )}
        <Composer disabled={!selected} onSubmit={(q) => ask(q)} />
        {!selected && (
          <p className="mt-2 text-center text-xs text-ink-soft">
            No collection available — set an API key or create a collection first.
          </p>
        )}
      </div>

      <SourceDrawer source={active} onClose={closeSource} />
    </div>
  );
}
