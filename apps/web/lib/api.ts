import { friendlyError, type TranscriptResponse } from "@shrutilipi/shared";

function apiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return base.replace(/\/$/, "");
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
