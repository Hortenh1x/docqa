"use client";

import { LockIcon } from "@/components/LockIcon";
import { joinNames, labelName, roleName, unlockingRoles } from "@/lib/access";
import type { AccessInfo, Role, SuggestedQuestion } from "@/lib/api/types";
import { QuestionChips } from "./QuestionChips";

/** Refusal is a first-class state: amber (honesty), never red (not an error).
 *  Two flavours: the corpus has nothing (classic), or the corpus has something the
 *  current role may not read — then the panel says so and offers the role that can. */
export function RefusalPanel({
  question,
  questions,
  onPick,
  access,
  roles,
  onViewAs,
}: {
  /** the question that was refused — left out of the alternatives */
  question?: string;
  questions?: SuggestedQuestion[] | null;
  onPick: (question: string) => void;
  access?: AccessInfo | null;
  roles?: Role[];
  onViewAs?: (role: string) => void;
}) {
  const hidden = access?.hidden_passages ?? 0;
  const hiddenLabels = access?.hidden_labels ?? [];
  const unlockers = hidden > 0 ? unlockingRoles(roles ?? [], hiddenLabels) : [];

  return (
    <div className="rounded-[10px] border border-pending/40 bg-pending/10 px-5 py-4">
      {hidden > 0 && access ? (
        <>
          <p className="flex items-center gap-2 font-medium text-ink">
            <LockIcon className="text-pending" />
            Not available at your access level.
          </p>
          <p className="mt-1 text-sm text-ink-soft">
            {describeHidden(access)} restricted to {joinNames(hiddenLabels.map(labelName))}.
            Nothing was invented to fill the gap.
          </p>
          {unlockers.length > 0 && onViewAs && (
            <div className="mt-3 flex flex-wrap gap-2">
              {unlockers.map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => onViewAs(role)}
                  className="rounded-[6px] border border-pending/60 bg-sheet px-3 py-1.5 text-sm text-ink hover:border-pending"
                >
                  View as {roleName(role)}
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <p className="font-medium text-ink">Not found in the documents.</p>
          <p className="mt-1 text-sm text-ink-soft">
            The collection doesn&rsquo;t contain information about this — so no answer was
            invented.
          </p>
        </>
      )}
      <div className="mt-3">
        <QuestionChips questions={questions} onPick={onPick} exclude={question} compact />
      </div>
    </div>
  );
}

/** "1 relevant passage exists, but it is" / "At least 20 relevant passages in 7 documents
 *  exist, but they are" — the probe window is finite, so a full window is a lower bound. */
function describeHidden(access: AccessInfo): string {
  const n = access.hidden_passages ?? 0;
  if (n === 1) return "1 relevant passage exists, but it is";
  const docs = access.hidden_documents ?? 0;
  const where = docs > 1 ? ` in ${docs} documents` : "";
  const atLeast = access.hidden_truncated ? "At least " : "";
  return `${atLeast}${n} relevant passages${where} exist, but they are`;
}
