import { NextRequest, NextResponse } from "next/server";
import { createHash, timingSafeEqual } from "node:crypto";

// Milestone 6: a deliberately minimal, temporary front door for /admin — no
// accounts, no password hashing, no session store. It exists only to keep
// the admin review UI (and the proxy routes under /admin/api/*, which hold
// the server-only FastAPI review token) from being reachable by anyone who
// just knows the URL. A real login system (accounts, audit trail, provider
// auth) is explicitly out of scope here and belongs in a future milestone.
//
// Named `proxy.ts` per Next.js 16's renamed convention (formerly
// `middleware.ts`) — it always runs on the Node.js runtime, which is what
// makes node:crypto's timingSafeEqual available below.

export const config = {
  matcher: ["/admin/:path*"],
};

function sha256(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

function safeEqual(a: string, b: string): boolean {
  // Hashing first avoids node:crypto's timingSafeEqual throwing on
  // differing input lengths, while keeping the comparison itself
  // constant-time — the same property app/api/routes.py's
  // hmac.compare_digest gives the backend's own admin token check.
  return timingSafeEqual(sha256(a), sha256(b));
}

function parseBasicAuth(header: string | null): { username: string; password: string } | null {
  if (!header || !header.startsWith("Basic ")) {
    return null;
  }
  let decoded: string;
  try {
    decoded = Buffer.from(header.slice("Basic ".length).trim(), "base64").toString("utf8");
  } catch {
    return null;
  }
  const separatorIndex = decoded.indexOf(":");
  if (separatorIndex === -1) {
    return null;
  }
  return {
    username: decoded.slice(0, separatorIndex),
    password: decoded.slice(separatorIndex + 1),
  };
}

export function proxy(request: NextRequest): NextResponse {
  const expectedUsername = process.env.ADMIN_UI_USERNAME;
  const expectedPassword = process.env.ADMIN_UI_PASSWORD;

  if (!expectedUsername || !expectedPassword) {
    // Unconfigured in this environment — behave as if /admin doesn't exist,
    // mirroring the backend's own "unconfigured admin surface 404s" rule
    // (app/api/routes.py:_require_admin_review) rather than a bare 403.
    return new NextResponse(null, { status: 404 });
  }

  const credentials = parseBasicAuth(request.headers.get("authorization"));
  if (
    credentials &&
    safeEqual(credentials.username, expectedUsername) &&
    safeEqual(credentials.password, expectedPassword)
  ) {
    return NextResponse.next();
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="GlowSearch Admin"' },
  });
}
