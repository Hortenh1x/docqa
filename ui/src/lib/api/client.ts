import type { Collection, DocumentOut, Problem, UsageSummary } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** The key lives in tab memory only — deliberately not persisted anywhere. */
let apiKey = process.env.NEXT_PUBLIC_DEMO_API_KEY ?? "";

export function setApiKey(key: string) {
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

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiKey}`);
  if (init.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const listCollections = () => api<Collection[]>("/v1/collections");

export const listDocuments = (collectionId: string) =>
  api<DocumentOut[]>(`/v1/collections/${collectionId}/documents`);

export const deleteDocument = (documentId: string) =>
  api<void>(`/v1/documents/${documentId}`, { method: "DELETE" });

/** The original uploaded file as a blob — the reader shows PDFs natively, text inline. */
export async function fetchDocumentFile(documentId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/v1/documents/${documentId}/file`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw await toApiError(res);
  return res.blob();
}

export const getUsage = (days = 30) => api<UsageSummary>(`/v1/usage?days=${days}`);

/** XHR instead of fetch: upload progress events are still fetch-less territory. */
export function uploadDocument(
  collectionId: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<{ id: string; status: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/v1/collections/${collectionId}/documents`);
    xhr.setRequestHeader("Authorization", `Bearer ${apiKey}`);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as { id: string; status: string });
      } else {
        const problem: Problem = xhr.response ?? { detail: xhr.statusText };
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
