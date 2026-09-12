import { apiFetch, ApiError } from "./client";
import type { AccessInfo, DonePayload, Problem, Source } from "./types";

/** Typed SSE events as the query endpoint emits them. */
export type QueryEvent =
  | { event: "meta"; data: { query_id: string; access: AccessInfo } }
  | { event: "sources"; data: { sources: Source[] } }
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: DonePayload }
  | { event: "error"; data: { code: string; message: string; reset_at?: string; retry_after_s?: number } };

/**
 * SSE over POST: EventSource can't POST, so we read the body stream manually.
 * Frames are separated by a blank line; a partial frame is carried into the next chunk.
 */
export async function streamQuery(
  body: { collection_id: string; question: string; role?: string },
  onEvent: (event: QueryEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await apiFetch("/v1/query", {
    method: "POST",
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });

  if (!res.ok || !res.headers.get("content-type")?.includes("text/event-stream")) {
    let problem: Problem = {};
    try {
      problem = await res.json();
    } catch {
      problem = { detail: res.statusText };
    }
    const retryAfter = res.headers.get("retry-after");
    throw new ApiError(res.status, problem, retryAfter ? Number(retryAfter) : null);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (frame: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) {
      onEvent({ event, data: JSON.parse(dataLines.join("")) } as QueryEvent);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      if (frame.trim()) dispatch(frame);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}
