import type { NextRequest } from "next/server";

import {
  AdminReviewNotConfiguredError,
  adminReviewNotConfiguredResponse,
  callAdminReviewApi,
  forwardJsonResponse,
} from "@/server/adminReviewClient";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const forwarded = new URLSearchParams();
  for (const key of ["limit", "after_id", "source"]) {
    const value = params.get(key);
    if (value !== null) forwarded.set(key, value);
  }
  const query = forwarded.toString();

  try {
    const response = await callAdminReviewApi(`/index/matches/pending${query ? `?${query}` : ""}`);
    return forwardJsonResponse(response);
  } catch (error) {
    if (error instanceof AdminReviewNotConfiguredError) {
      return adminReviewNotConfiguredResponse();
    }
    throw error;
  }
}
