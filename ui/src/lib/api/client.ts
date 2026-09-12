import type {
  Collection,
  DocumentOut,
  IngestStatus,
  Problem,
  Role,
  UsageSummary,
  AccountSession,
  Budget,
  SiteInfo,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** The key lives in tab memory only — deliberately not persisted anywhere. */
export const ACCOUNTS_ENABLED = process.env.NEXT_PUBLIC_ACCOUNTS_ENABLED === "true";
let apiKey = ACCOUNTS_ENABLED ? "" : process.env.NEXT_PUBLIC_DEMO_API_KEY ?? "";
let requests = new AbortController();

export function abortRequests() {
  requests.abort();
  requests = new AbortController();
}

let browserSession: AccountSession | null = null;
let sessionHandler: ((session: AccountSession | null) => void) | null = null;
export function onSessionChange(handler: ((session: AccountSession | null) => void) | null) {
  sessionHandler = handler;
}
export function acceptSession(
  session: AccountSession | null,
  { notify = true }: { notify?: boolean } = {},
) {
  abortRequests();
  browserSession = session;
  if (notify) sessionHandler?.(session);
}
const identity = (session: AccountSession | null) =>
  `${session?.user?.id ?? "guest"}:${session?.user?.email_verified ?? false}`;

export async function fetchSession(): Promise<AccountSession> {
  const signal = requests.signal;
  const res = await fetch(`${API_BASE}/v1/auth/session`, {
    credentials: "include", cache: "no-store", signal,
  });
  if (!res.ok) throw await toApiError(res);
  const session = await res.json() as AccountSession;
  signal.throwIfAborted();
  return session;
}

/** Revalidate before writes so an old tab cannot act as a newly signed-in account. */
async function mutationSession(): Promise<string> {
  if (!browserSession) throw new ApiError(401, { detail: "Your session is loading. Try again." });
  const current = await fetchSession().catch((error: unknown) => {
    if (error instanceof ApiError && error.code === "invalid_session") acceptSession(null);
    throw error;
  });
  if (identity(current) !== identity(browserSession)) {
    acceptSession(current);
    throw new DOMException("Account changed. Please repeat the action.", "AbortError");
  }
  browserSession = current;
  if (!current.csrf_token) throw new ApiError(503, { detail: "Browser accounts are unavailable." });
  return current.csrf_token;
}

export function setApiKey(key: string) {
  abortRequests();
  apiKey = key.trim();
}

export function getApiKey(): string {
  return apiKey;
}

export class ApiError extends Error {
  readonly problem: Problem;
  readonly status: number;
  readonly retryAfterS: number | null;

  constructor(status: number, problem: Problem, retryAfterS: number | null = null) {
    super(problem.detail ?? problem.title ?? `HTTP ${status}`);
    this.status = status;
    this.problem = problem;
    this.retryAfterS = retryAfterS;
  }

  get code(): string {
    return this.problem.code ?? "unknown";
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let problem: Problem = {};
  try {
    problem = await res.json();
  } catch {
    problem = { detail: res.statusText };
  }
  const retryAfter = res.headers.get("retry-after");
  return new ApiError(res.status, problem, retryAfter ? Number(retryAfter) : null);
}

/** Every request belongs to the current key, including streams and file downloads. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const requestSignal = requests.signal;
  const headers = new Headers(init.headers);
  if (ACCOUNTS_ENABLED) {
    headers.delete("Authorization");
    if (!["GET", "HEAD"].includes((init.method ?? "GET").toUpperCase())) {
      headers.set("X-CSRF-Token", await mutationSession());
    }
  } else headers.set("Authorization", `Bearer ${apiKey}`);
  requestSignal.throwIfAborted();
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_BASE}${path}`, {
    ...init, headers,
    ...(ACCOUNTS_ENABLED ? { credentials: "include" as const, cache: "no-store" as const } : {}),
    signal: init.signal ? AbortSignal.any([init.signal, requestSignal]) : requestSignal,
  });
  if (ACCOUNTS_ENABLED && res.status === 401) {
    const problem = await res.clone().json().catch(() => ({})) as Problem;
    if (problem.code === "invalid_session") acceptSession(null);
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const listCollections = () => api<Collection[]>("/v1/collections");

export const listRoles = () => api<Role[]>("/v1/roles");

export const listDocuments = (collectionId: string) =>
  api<DocumentOut[]>(`/v1/collections/${collectionId}/documents`);

/** One page of a collection's documents plus the collection total (X-Total-Count). */
export async function listDocumentsPage(
  collectionId: string,
  limit: number,
  offset: number,
): Promise<{ documents: DocumentOut[]; total: number }> {
  const res = await apiFetch(
    `/v1/collections/${collectionId}/documents?limit=${limit}&offset=${offset}`,
  );
  if (!res.ok) throw await toApiError(res);
  const documents = (await res.json()) as DocumentOut[];
  const total = Number(res.headers.get("x-total-count") ?? documents.length);
  return { documents, total };
}

export const getIngestStatus = (collectionId: string) =>
  api<IngestStatus>(`/v1/collections/${collectionId}/ingest-status`);

export const deleteDocument = (documentId: string) =>
  api<void>(`/v1/documents/${documentId}`, { method: "DELETE" });

/** The original uploaded file as a blob — the reader shows PDFs natively, text inline. */
export async function fetchDocumentFile(documentId: string, role?: string): Promise<Blob> {
  const query = role ? `?role=${encodeURIComponent(role)}` : "";
  const res = await apiFetch(`/v1/documents/${documentId}/file${query}`);
  if (!res.ok) throw await toApiError(res);
  return res.blob();
}

export const getUsage = (days = 30) => api<UsageSummary>(`/v1/usage?days=${days}`);

/** XHR instead of fetch: upload progress events are still fetch-less territory. */
export async function uploadDocument(
  collectionId: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<{ id: string; status: string }> {
  const signal = requests.signal;
  const csrf = ACCOUNTS_ENABLED ? await mutationSession() : null;
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onloadend = () => signal.removeEventListener("abort", abort);
    xhr.onabort = () => reject(new DOMException("API key changed", "AbortError"));
    xhr.open("POST", `${API_BASE}/v1/collections/${collectionId}/documents`);
    if (ACCOUNTS_ENABLED) {
      xhr.withCredentials = true;
      xhr.setRequestHeader("X-CSRF-Token", csrf!);
    } else xhr.setRequestHeader("Authorization", `Bearer ${apiKey}`);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as { id: string; status: string });
      } else {
        const problem: Problem = xhr.response ?? { detail: xhr.statusText };
        if (ACCOUNTS_ENABLED && xhr.status === 401 && problem.code === "invalid_session") acceptSession(null);
        const retryAfter = xhr.getResponseHeader("retry-after");
        reject(new ApiError(xhr.status, problem, retryAfter ? Number(retryAfter) : null));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, { detail: "Network error" }));
    xhr.send((() => {
      const form = new FormData();
      form.append("file", file);
      return form;
    })());
  });
}

export const getBudget = () => api<Budget>("/v1/budget");
export const getSite = () => api<SiteInfo>("/v1/site");
export const reprocessDocument = (id: string) =>
  api<{ id: string; status: string }>(`/v1/documents/${id}/reprocess`, { method: "POST", body: "{}" });

export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Check your connection and try again.";
  if (error.code === "quota_exceeded") {
    const reset = typeof error.problem.reset_at === "string" ? error.problem.reset_at : null;
    return `Daily budget used. ${reset ? `Resets ${new Date(reset).toLocaleString("en-GB", { timeZone: "UTC" })} UTC.` : "Try again after the next 00:00 UTC reset."}`;
  }
  if (error.code === "budget_unavailable") return "Budget checks are temporarily unavailable. Please try again later.";
  // Validation responses can contain a list; never stringify it (it may include submitted input).
  return typeof error.message === "string" && error.message !== "[object Object]"
    ? error.message : "Check the form fields and try again.";
}
