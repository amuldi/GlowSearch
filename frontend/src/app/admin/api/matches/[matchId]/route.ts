import {
  AdminReviewNotConfiguredError,
  adminReviewNotConfiguredResponse,
  callAdminReviewApi,
  forwardJsonResponse,
} from "@/server/adminReviewClient";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ matchId: string }> },
) {
  const { matchId } = await params;
  try {
    const response = await callAdminReviewApi(`/index/matches/${encodeURIComponent(matchId)}`);
    return forwardJsonResponse(response);
  } catch (error) {
    if (error instanceof AdminReviewNotConfiguredError) {
      return adminReviewNotConfiguredResponse();
    }
    throw error;
  }
}
