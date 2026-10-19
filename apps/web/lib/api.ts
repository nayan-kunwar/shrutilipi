import { friendlyError, type TranscriptResponse } from "@shrutilipi/shared";

function apiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return base.replace(/\/$/, "");
}

/**
 * Wake/keep-warm probe for the Render free instance.
 *
 * A GET /api/wake costs nothing upstream (no provider call, not rate-limited)
 * and its mere arrival starts a boot if the instance is asleep. Render holds
 * the request open while the instance starts, so the timeout is generous.
 *
 * The path is /api/wake rather than /health on purpose: some adblock filter
 * lists block health-style URLs client-side (net::ERR_BLOCKED_BY_CLIENT),
 * which the app cannot distinguish from a genuinely dead server.
 */
export async function pingHealth(timeoutMs = 120_000): Promise<boolean> {
  try {
    const res = await fetch(`${apiBase()}/api/wake`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchTranscript(url: string, lang = "en"): Promise<TranscriptResponse> {
  const res = await fetch(
    `${apiBase()}/api/transcript?url=${encodeURIComponent(url)}&lang=${encodeURIComponent(lang)}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* keep default */
    }
    throw new Error(friendlyError(res.status, detail));
  }
  return (await res.json()) as TranscriptResponse;
}

export type { TranscriptResponse };
