export function ClarificationPanel({ question }: { question: string }) {
  return <div className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 text-[15px] leading-7" role="status">
    <p className="font-data mb-1 text-xs text-ink-soft">Clarification needed</p>
    <p>{question}</p>
  </div>;
}
