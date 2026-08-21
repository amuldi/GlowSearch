import { NextResponse } from "next/server";

// Server-only. This is the ONLY module that reads GLOWSEARCH_ADMIN_REVIEW_TOKEN
// and attaches it to a request. Do not import this from a "use client" file —
// there is no NEXT_PUBLIC_ prefix on the token on purpose, so Next.js never
// inlines it into the browser bundle, but only if this module is never
// pulled into client-side code. Only import it from files under
// src/app/admin/api/**/route.ts (Next.js Route Handlers, which the framework
// itself never lets a Client Component import).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class AdminReviewNotConfiguredError extends Error {
  constructor() {
    super("GLOWSEARCH_ADMIN_REVIEW_TOKEN is not set on the server.");
    this.name = "AdminReviewNotConfiguredError";
  }
}

/**
 * Calls the FastAPI admin review API (`/index/matches/*`) with the
 * server-only bearer token attached. `path` must start with `/index/matches`
 * — this is not a general-purpose proxy.
 */
export async function callAdminReviewApi(path: string, init: RequestInit = {}): Promise<Response> {
  const token = process.env.GLOWSEARCH_ADMIN_REVIEW_TOKEN;
  if (!token) {
    throw new AdminReviewNotConfiguredError();
  }
  if (!path.startsWith("/index/matches")) {
    throw new Error(`callAdminReviewApi: unexpected path ${path}`);
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

/**
 * Forwards a FastAPI response's status and JSON body back to the browser
 * unchanged — the review API already follows the "no sensitive detail in
 * error bodies" principle (milestone 4), so the proxy doesn't need to
 * reinterpret its errors, only pass them through.
 */
export async function forwardJsonResponse(response: Response): Promise<NextResponse> {
  const text = await response.text();
  return new NextResponse(text || null, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

/** Standard response for a proxy route when the server-side token isn't
 * configured — deliberately generic, mirrors the backend's own
 * sensitive-info non-disclosure stance (milestone 4 §6). */
export function adminReviewNotConfiguredResponse(): NextResponse {
  return NextResponse.json({ detail: "Admin review API is not configured." }, { status: 500 });
}
