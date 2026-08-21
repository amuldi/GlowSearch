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

/** A response came back, but with a non-2xx status. `status` mirrors the
 * proxy's forwarded FastAPI status exactly (404/403/409/500/... —
 * `frontend/src/server/adminReviewClient.ts` passes it through unchanged),
 * so callers can branch on real backend semantics. */
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

/** `fetch` itself threw — DNS/connection failure, offline, CORS, the dev
 * server not running, etc. No HTTP response was ever received, so there is
 * no status to branch on (distinct from `AdminReviewApiError`). */
export class AdminReviewNetworkError extends Error {
  constructor(cause?: unknown) {
    super("네트워크 요청에 실패했습니다.");
    this.name = "AdminReviewNetworkError";
    if (cause !== undefined) this.cause = cause;
  }
}

/** The request didn't complete within `DEFAULT_TIMEOUT_MS`. Neither the
 * proxy route nor the FastAPI backend enforces a server-side timeout today
 * (`callAdminReviewApi` awaits `fetch` unconditionally) — this is a
 * client-side backstop so a hung upstream can't leave the review UI stuck
 * on "처리 중" forever. */
export class AdminReviewTimeoutError extends Error {
  constructor() {
    super("요청이 시간 초과되었습니다.");
    this.name = "AdminReviewTimeoutError";
  }
}

/** A response came back with a 2xx status but a body that isn't valid
 * JSON — e.g. the proxy or FastAPI itself crashed mid-response, or an
 * intermediary (dev proxy, load balancer) returned an HTML error page with
 * a 200. Kept distinct from `AdminReviewApiError` because `status` alone
 * (2xx) would otherwise look like success to a caller only checking status. */
export class AdminReviewMalformedResponseError extends Error {
  status: number;
  constructor(status: number) {
    super("서버 응답을 해석할 수 없습니다.");
    this.name = "AdminReviewMalformedResponseError";
    this.status = status;
  }
}

const DEFAULT_TIMEOUT_MS = 15_000;

async function parseErrorDetail(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** Shared fetch+parse path for every call below: applies the client-side
 * timeout, tells a real network failure apart from a timeout apart from an
 * HTTP error status apart from an unparsable success body, and forwards an
 * externally-supplied `signal` (e.g. a component unmount abort) through
 * untouched rather than swallowing it as a timeout. */
async function requestJson<T>(url: string | URL, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = init.signal ?? null;
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    if (externalSignal?.aborted) {
      throw error; // real cancellation from the caller — let it propagate as-is
    }
    if (controller.signal.aborted) {
      throw new AdminReviewTimeoutError();
    }
    throw new AdminReviewNetworkError(error);
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) externalSignal.removeEventListener("abort", onExternalAbort);
  }

  if (!response.ok) {
    throw new AdminReviewApiError(response.status, await parseErrorDetail(response));
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new AdminReviewMalformedResponseError(response.status);
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

  return requestJson<PendingMatchListResponse>(url, { signal: params.signal });
}

export async function fetchMatchDetail(matchId: string, signal?: AbortSignal): Promise<MatchDetail> {
  return requestJson<MatchDetail>(`/admin/api/matches/${encodeURIComponent(matchId)}`, { signal });
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
  return requestJson<MatchReviewResponse>(`/admin/api/matches/${encodeURIComponent(matchId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision: params.decision,
      reviewer: params.reviewer,
      note: params.note ?? undefined,
      expected_updated_at: params.expectedUpdatedAt ?? undefined,
    }),
  });
}
