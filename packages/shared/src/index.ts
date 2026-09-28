/**
 * @shrutilipi/shared — the contract between the FastAPI backend and every client.
 *
 * Pure, environment-free code only. Anything that touches `process.env` or the
 * network stays in apps/web, so this package stays importable from a plain
 * Node script or a future worker with no shims.
 *
 * The two rules that make this worth extracting:
 *   1. `friendlyError` is the single mapping from backend `detail` codes to
 *      user-facing copy. It lives here so a new detail code can never be added
 *      in the frontend without a decision about what to say.
 *   2. `formatTime` is the TypeScript half of a two-language pair — the Python
 *      twin is `format_time()` in tools/fetch.py. Keep them in sync: a 5-minute
 *      video must read `5:30`, never `0:05:30`.
 */

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

/** The `detail` codes `apps/api/main.py::_map_error` can return. */
export type TranscriptErrorDetail =
  | "invalid_url"
  | "no_captions"
  | "video_unavailable"
  | "youtube_blocked"
  | "provider_unavailable"
  | "transcript_fetch_failed";

/**
 * The canonical origin, used for `metadataBase`, the sitemap and robots.txt.
 *
 * This used to be copy-pasted into three files, which meant a domain change
 * could silently update two of three. It lives here so there is one place to
 * edit — see docs/operations.md §8.
 */
export const SITE_URL = "https://frontend-six-woad-540yl4bn2c.vercel.app";

/**
 * Map an HTTP status + backend `detail` code to a sentence worth showing a user.
 * Unknown codes fall back to the raw detail so a new backend code is visible in
 * the UI rather than swallowed.
 */
export function friendlyError(status: number, detail: string): string {
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

/** Seconds -> `m:ss`, or `h:mm:ss` once the video runs past an hour. */
export function formatTime(s: number): string {
  const total = Math.max(0, Math.floor(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
