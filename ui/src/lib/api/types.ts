export interface Collection {
  id: string;
  name: string;
  slug: string;
  embedding_model: string;
  read_only: boolean;
  created_at: string;
}

export interface DocumentOut {
  id: string;
  collection_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  page_count: number | null;
  created_at: string;
  processed_at: string | null;
}

export interface Source {
  n: number;
  document_id: string;
  filename: string;
  pages: [number, number] | null;
  section: string | null;
  snippet: string;
  score: number;
}

export interface Usage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cost_usd: number | null;
}

export interface DonePayload {
  answer: string | null;
  refused: boolean;
  reason: string | null;
  confidence: number | null;
  usage: Usage;
  latency_ms: number;
  model: string | null;
}

export interface UsageDay {
  date: string;
  queries: number;
  cost_usd: number;
}

export interface UsageSummary {
  days: number;
  queries: number;
  refused: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  avg_latency_ms: number | null;
  daily: UsageDay[];
}

/** RFC 9457 problem+json body, as our API emits it. */
export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  request_id?: string;
  [extra: string]: unknown;
}
