"use client";

import { useRole } from "@/app/providers";
import { LockIcon } from "@/components/LockIcon";
import { roleName, unlocks } from "@/lib/access";
import type { SuggestedQuestion } from "@/lib/api/types";

/** The collection's own LLM-generated starter questions (3, refreshed whenever its
 *  ingestion settles). No static fallback on purpose: an empty collection — or one
 *  whose questions are still generating — shows no chips rather than someone
 *  else's questions. A chip the current role cannot answer wears a lock and the role
 *  that can; clicking it still asks — the refusal it gets is the demo. */
export function QuestionChips({
  questions,
  onPick,
  exclude,
  compact = false,
}: {
  questions?: SuggestedQuestion[] | null;
  onPick: (question: string) => void;
  /** a question to leave out — the one just asked, on a refusal panel */
  exclude?: string;
  compact?: boolean;
}) {
  const { roles, role } = useRole();
  const shown = (questions ?? []).filter(
    (q) => !exclude || q.question.trim().toLowerCase() !== exclude.trim().toLowerCase(),
  );
  if (!shown.length) return null;
  return (
    <div className={`flex flex-wrap gap-2 ${compact ? "" : "max-w-xl justify-center"}`}>
      {shown.map(({ question, min_role }) => {
        const locked = !unlocks(roles, role, min_role);
        return (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            aria-label={locked ? `${question} (requires the ${roleName(min_role)} role)` : undefined}
            className={
              compact
                ? "inline-flex items-center gap-1.5 rounded-full border border-hairline bg-sheet px-3 py-1 text-xs text-ink-soft hover:text-ink"
                : "inline-flex items-center gap-1.5 rounded-full border border-hairline bg-sheet px-3.5 py-1.5 text-sm text-ink-soft shadow-card hover:border-stamp/40 hover:text-ink"
            }
          >
            {question}
            {locked && (
              <span className="font-data inline-flex items-center gap-1 text-[11px] text-ink-soft">
                <LockIcon />
                {roleName(min_role)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
