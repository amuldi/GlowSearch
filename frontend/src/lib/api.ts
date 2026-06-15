import type {
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

export async function organizeEditorBatch(
  text: string,
  signal?: AbortSignal,
): Promise<EditorBatchResponse> {
  const url = new URL("/editor/batch", API_BASE_URL);
  const response = await fetch(url, {
    method: "POST",
    signal,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text, limit: 5 }),
  });

  if (!response.ok) {
    throw new Error(`편집자 정리 요청 실패: ${response.status}`);
  }
  return response.json() as Promise<EditorBatchResponse>;
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
