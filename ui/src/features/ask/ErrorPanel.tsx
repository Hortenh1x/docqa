"use client";

import { useEffect, useState } from "react";
import type { AskError } from "./state";

export function ErrorPanel({ error, onRetry }: { error: AskError; onRetry: () => void }) {
  const [secondsLeft, setSecondsLeft] = useState(error.retryAfterS ?? 0);

  useEffect(() => {
    setSecondsLeft(error.retryAfterS ?? 0);
    if (!error.retryAfterS) return;
    const timer = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [error]);

  const rateLimited = error.code === "rate_limited";
  const quota = error.code === "quota_exceeded";
  const resetTime = error.resetAt ? new Date(error.resetAt).getTime() : null;
  return (
    <div className="rounded-[10px] border border-error/40 bg-error/10 px-5 py-4">
      <p className="font-medium text-ink">
        {quota ? "Daily budget used" : rateLimited ? "Demo limit reached" : "Something went wrong"}
      </p>
      <p className="mt-1 text-sm text-ink-soft">
        {quota
          ? `Your allowance resets ${error.resetAt ? new Date(error.resetAt).toLocaleString("en-GB", { timeZone: "UTC" }) : "at 00:00"} UTC. Guest usage carries over after sign-in.`
          : rateLimited
          ? secondsLeft > 0
            ? `Try again in ${secondsLeft}s.`
            : "You can try again now."
          : error.message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        disabled={(rateLimited && secondsLeft > 0) || (quota && (resetTime === null || resetTime > Date.now()))}
        className="mt-3 rounded-[6px] border border-hairline bg-sheet px-3.5 py-1.5 text-sm disabled:opacity-40"
      >
        Retry
      </button>
    </div>
  );
}
