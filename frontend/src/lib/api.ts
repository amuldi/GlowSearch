import type {
  DiagnosticsResponse,
  EditorBatchResponse,
  EditorConfirmRequest,
  EditorConfirmResponse,
  SearchParams,
  SearchResponse,
  SuggestionResponse,
} from "@/types/product";

const DEFAULT_API_BASE_URL =
  process.env.NODE_ENV === "production"
    ? "https://glowsearch-backend.onrender.com"
    : "http://localhost:8000";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
const EDITOR_BATCH_RETRY_DELAYS_MS = [1200, 3000, 6000, 10000];

export async function searchProducts(
  params: SearchParams,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const url = new URL("/search", API_BASE_URL);
  url.searchParams.set("q", params.query);

  if (params.limit) url.searchParams.set("limit", String(params.limit));

  const response = await fetch(url, {
    method: "GET",
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`검색 요청 실패: ${response.status}`);
  }
  return response.json() as Promise<SearchResponse>;
}

export async function fetchSearchSuggestions(
  query: string,
  signal?: AbortSignal,
): Promise<SuggestionResponse> {
  const url = new URL("/suggest", API_BASE_URL);
  url.searchParams.set("q", query);
  url.searchParams.set("limit", "10");

  const response = await fetch(url, {
    method: "GET",
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`추천 검색어 요청 실패: ${response.status}`);
  }
  return response.json() as Promise<SuggestionResponse>;
}

export async function fetchDiagnostics(signal?: AbortSignal): Promise<DiagnosticsResponse> {
  const url = new URL("/diagnostics", API_BASE_URL);
  const response = await fetch(url, {
    method: "GET",
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`운영 상태 요청 실패: ${response.status}`);
  }
  return response.json() as Promise<DiagnosticsResponse>;
}

export async function organizeEditorBatch(
  text: string,
  signal?: AbortSignal,
): Promise<EditorBatchResponse> {
  const url = new URL("/editor/batch", API_BASE_URL);
  const body = JSON.stringify({ text, limit: 5 });

  for (let attempt = 0; attempt <= EDITOR_BATCH_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const response = await fetch(url, {
        method: "POST",
        signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body,
      });

      if (response.ok) {
        return response.json() as Promise<EditorBatchResponse>;
      }
      if (!isRetriableEditorBatchStatus(response.status) || attempt >= EDITOR_BATCH_RETRY_DELAYS_MS.length) {
        throw new Error(`편집자 정리 요청 실패: ${response.status}`);
      }
    } catch (error) {
      if (signal?.aborted || attempt >= EDITOR_BATCH_RETRY_DELAYS_MS.length) {
        throw error;
      }
    }
    await delay(EDITOR_BATCH_RETRY_DELAYS_MS[attempt]);
  }
  throw new Error("편집자 정리 요청 실패");
}

export async function confirmEditorCandidate(
  payload: EditorConfirmRequest,
  signal?: AbortSignal,
): Promise<EditorConfirmResponse> {
  const url = new URL("/editor/confirm", API_BASE_URL);
  const response = await fetch(url, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`편집자 확정 저장 실패: ${response.status}`);
  }
  return response.json() as Promise<EditorConfirmResponse>;
}

function isRetriableEditorBatchStatus(status: number) {
  return status === 408 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
