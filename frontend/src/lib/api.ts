import type {
  DiagnosticsResponse,
  EditorBatchItem,
  EditorBatchProgress,
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
const EDITOR_BATCH_LINE_CONCURRENCY = 3;

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
  limit = 5,
): Promise<EditorBatchResponse> {
  const url = new URL("/editor/batch", API_BASE_URL);
  const body = JSON.stringify({ text, limit });

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

export async function organizeEditorBatchByLines(
  text: string,
  options: {
    signal?: AbortSignal;
    limit?: number;
    onProgress?: (progress: EditorBatchProgress) => void;
  } = {},
): Promise<EditorBatchResponse> {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const total = lines.length;
  const items: Array<EditorBatchItem | undefined> = new Array(total);
  let completed = 0;
  let nextIndex = 0;

  if (!total) {
    return { count: 0, items: [] };
  }

  const publish = () => {
    options.onProgress?.({
      completed,
      total,
      response: {
        count: items.filter(Boolean).length,
        items: items.filter((item): item is EditorBatchItem => Boolean(item)),
      },
    });
  };

  const worker = async () => {
    while (nextIndex < total) {
      const index = nextIndex;
      nextIndex += 1;
      const line = lines[index];
      try {
        const response = await organizeEditorBatch(line, options.signal, options.limit ?? 5);
        items[index] = response.items[0] ?? fallbackEditorBatchItem(line);
      } catch (error) {
        if (options.signal?.aborted) {
          throw error;
        }
        items[index] = fallbackEditorBatchItem(line);
      } finally {
        completed += 1;
        publish();
      }
    }
  };

  const workers = Array.from(
    { length: Math.min(EDITOR_BATCH_LINE_CONCURRENCY, total) },
    () => worker(),
  );
  await Promise.all(workers);

  const response = {
    count: total,
    items: items.map((item, index) => item ?? fallbackEditorBatchItem(lines[index])),
  };
  options.onProgress?.({ completed: total, total, response });
  return response;
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

function fallbackEditorBatchItem(rawText: string): EditorBatchItem {
  const shade = parseFallbackShade(rawText);
  const productQuery = rawText
    .replace(shade.token ?? "", "")
    .replace(/\s+/g, " ")
    .trim() || rawText;
  return {
    raw_text: rawText,
    parsed: {
      raw_text: rawText,
      brand_query: null,
      brand_en: null,
      product_query: productQuery,
      shade_query: shade.value,
      shade_code: shade.code,
      shade_name: shade.name,
      normalized_query: productQuery,
    },
    status: "수동 확인 필요",
    candidates: [],
  };
}

function parseFallbackShade(rawText: string) {
  const hashMatch = rawText.match(/#([0-9A-Za-z가-힣._-]+)/);
  if (hashMatch) {
    const value = hashMatch[1];
    return {
      token: hashMatch[0],
      value,
      code: /[0-9]/.test(value) ? value : null,
      name: /[0-9]/.test(value) ? null : value,
    };
  }

  const numberMatch = rawText.match(/([0-9A-Za-z._-]+)\s*호/);
  if (numberMatch) {
    return {
      token: numberMatch[0],
      value: numberMatch[0],
      code: numberMatch[1],
      name: null,
    };
  }

  return { token: null, value: null, code: null, name: null };
}
