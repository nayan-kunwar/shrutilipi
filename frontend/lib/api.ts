export interface TranscriptSegment {
  start: number;
  duration: number;
  text: string;
}

export interface TranscriptResponse {
  videoId: string;
  title: string | null;
  language: string;
  plainText: string;
  segments: TranscriptSegment[];
}

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

function friendlyError(status: number, detail: string): string {
  switch (detail) {
    case "invalid_url":
      return "That doesn't look like a valid YouTube URL or video ID.";
    case "no_captions":
      return "No captions found for this video. Try another video (Whisper fallback coming in v2).";
    case "video_unavailable":
      return "Video is unavailable, private, or age-restricted.";
    case "youtube_blocked":
      return "YouTube temporarily blocked the request. Wait a minute and retry.";
    case "provider_unavailable":
      return "Transcript services are busy or out of quota — retry in a few minutes.";
    case "transcript_fetch_failed":
      return "Couldn't fetch the transcript. Please retry.";
    default:
      return status === 404 ? "Transcript not found for this video." : detail;
  }
}
