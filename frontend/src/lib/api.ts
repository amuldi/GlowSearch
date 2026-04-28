import type { SearchParams, SearchResponse } from "@/types/product";

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

  if (params.brand) url.searchParams.set("brand", params.brand);
  if (params.minPrice) url.searchParams.set("min_price", params.minPrice);
  if (params.maxPrice) url.searchParams.set("max_price", params.maxPrice);
  if (params.hasShade !== undefined) url.searchParams.set("has_shade", String(params.hasShade));
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
