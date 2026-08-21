// Client for the admin review proxy (milestone 6/7). Deliberately calls only
// RELATIVE paths under /admin/api/matches/* — never NEXT_PUBLIC_API_BASE_URL,
// never any token. The browser already carries the Basic Auth credential
// (frontend/src/proxy.ts) for every same-origin request automatically once
// entered once; this file has nothing to add there. Do not import
// frontend/src/server/adminReviewClient.ts here or anywhere under "use
// client" — that module is server-only and holds the real FastAPI token.

import type {
  MatchDetail,
  MatchReviewDecision,
  MatchReviewResponse,
  PendingMatchListResponse,
} from "@/types/review";

export class AdminReviewApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`관리자 검토 API 요청 실패: ${status}`);
    this.name = "AdminReviewApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseErrorDetail(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchPendingMatches(params: {
  limit?: number;
  afterId?: number | null;
  source?: string | null;
  signal?: AbortSignal;
}): Promise<PendingMatchListResponse> {
  const url = new URL("/admin/api/matches/pending", window.location.origin);
  if (params.limit) url.searchParams.set("limit", String(params.limit));
  if (params.afterId != null) url.searchParams.set("after_id", String(params.afterId));
  if (params.source) url.searchParams.set("source", params.source);

  const response = await fetch(url, { signal: params.signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new AdminReviewApiError(response.status, await parseErrorDetail(response));
  return response.json() as Promise<PendingMatchListResponse>;
}

export async function fetchMatchDetail(matchId: string, signal?: AbortSignal): Promise<MatchDetail> {
  const response = await fetch(`/admin/api/matches/${encodeURIComponent(matchId)}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new AdminReviewApiError(response.status, await parseErrorDetail(response));
  return response.json() as Promise<MatchDetail>;
}

export async function reviewMatch(
  matchId: string,
  params: {
    decision: MatchReviewDecision;
    reviewer: string;
    note?: string | null;
    expectedUpdatedAt?: string | null;
  },
): Promise<MatchReviewResponse> {
  const response = await fetch(`/admin/api/matches/${encodeURIComponent(matchId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision: params.decision,
      reviewer: params.reviewer,
      note: params.note ?? undefined,
      expected_updated_at: params.expectedUpdatedAt ?? undefined,
    }),
  });
  if (!response.ok) throw new AdminReviewApiError(response.status, await parseErrorDetail(response));
  return response.json() as Promise<MatchReviewResponse>;
}
