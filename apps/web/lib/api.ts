import {
  friendlyError,
  type SummaryResponse,
  type TranscriptResponse,
} from "@shrutilipi/shared";

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

/**
 * Generate a summary on demand.
 *
 * Only the video id is sent — never transcript text — so the API summarizes
 * its own fetched transcript and cannot be used as an open LLM proxy. The
 * request is made only when the user clicks the button, never on page load.
 */
export async function fetchSummary(videoId: string, lang = "en"): Promise<SummaryResponse> {
  const res = await fetch(`${apiBase()}/api/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ videoId, lang }),
    // The LLM call plus a possible transcript refetch on a cold cache can
    // take a while; the server bounds each half at 30s.
    signal: AbortSignal.timeout(75_000),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      // FastAPI validation errors use an array; fall back to the status.
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* keep default */
    }
    throw new Error(friendlyError(res.status, detail));
  }
  return (await res.json()) as SummaryResponse;
}

export type { SummaryResponse, TranscriptResponse };
