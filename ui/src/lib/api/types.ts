/** A starter question and the least-privileged access role that can answer it. */
export interface SuggestedQuestion {
  question: string;
  min_role: string;
}

/** An access role the API accepts on queries (GET /v1/roles), in privilege order. */
export interface Role {
  role: string;
  labels: string[];
  description: string;
  default: boolean;
}

/** What a query reveals about access: the role it ran as and, in reveal mode, what it
 *  could not see (null = not revealed). */
export interface AccessInfo {
  role: string;
  /** filtered-out passages above the relevance floor (null = not revealed) */
  hidden_passages: number | null;
  hidden_labels: string[] | null;
  /** distinct documents those passages come from */
  hidden_documents: number | null;
  /** how many of them scored at least as well as the best passage the role could see */
  hidden_outranking: number | null;
  /** the probe window was full — hidden_passages is a lower bound */
  hidden_truncated: boolean | null;
}

export interface Collection {
  id: string;
  name: string;
  slug: string;
  embedding_model: string;
  read_only: boolean;
  is_public?: boolean;
  owned?: boolean;
  writable?: boolean;
  /** 3 LLM-drafted starter questions; null until the first ingestion settles. */
  suggested_questions: SuggestedQuestion[] | null;
  /** restricted content labels present in the collection (empty = nothing restricted) */
  access_labels: string[];
  /** documents in the collection, any status */
  document_count: number;
  created_at: string;
}

export interface IngestStatus {
  pending: number;
  processing: number;
  ready: number;
  failed: number;
  embedded_tokens: number;
  embedding_model: string;
  price_per_1m_tokens: number | null;
  embedding_cost_usd: number | null;
  eta_seconds: number | null;
  suggested_questions: SuggestedQuestion[] | null;
  access: { chunks_by_label: Record<string, number>; restricted_chunks: number };
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
  /** restricted content labels found in the document's sections (empty = all open) */
  access_labels: string[];
}

export interface Source {
  n: number;
  document_id: string;
  filename: string;
  pages: [number, number] | null;
  section: string | null;
  snippet: string;
  score: number;
  /** content label of the chunk ("all" = open) */
  access_label: string;
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

export interface AccountSession {
  user: { id: string; email: string; email_verified: boolean; tenant_id: string } | null;
  csrf_token: string | null;
  registration_available: boolean; google_available?: boolean;
}
export type Budget = { enabled: false } | {
  enabled: true; limit_usd: string; spent_usd: string; reserved_usd: string;
  remaining_usd: string; reset_at: string; limited_by: "ip" | "account";
};
export interface SiteInfo {
  accounts_enabled: boolean;
  upload_max_mb: number;
  operator_contact: string | null;
  providers: { name: string; receives: string }[];
  purpose: string;
  document_privacy: string;
}

/** Original-file capacity across every collection owned by the current account. */
export interface StorageUsage {
  used_bytes: number;
  limit_bytes: number;
  remaining_bytes: number;
  document_count: number;
}
