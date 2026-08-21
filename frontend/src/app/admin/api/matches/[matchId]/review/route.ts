import {
  AdminReviewNotConfiguredError,
  adminReviewNotConfiguredResponse,
  callAdminReviewApi,
  forwardJsonResponse,
} from "@/server/adminReviewClient";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ matchId: string }> },
) {
  const { matchId } = await params;
  const body = await request.text();
  try {
    const response = await callAdminReviewApi(`/index/matches/${encodeURIComponent(matchId)}/review`, {
      method: "POST",
      body,
    });
    return forwardJsonResponse(response);
  } catch (error) {
    if (error instanceof AdminReviewNotConfiguredError) {
      return adminReviewNotConfiguredResponse();
    }
    throw error;
  }
}
