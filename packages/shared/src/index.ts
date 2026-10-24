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

/** On-demand summary: generated only when the user clicks the button. */
export interface SummaryResponse {
  summary: string;
  model: string;
  cached: boolean;
}

/** The `detail` codes the API can return (`_map_error` plus the rate limiter). */
export type TranscriptErrorDetail =
  | "invalid_url"
  | "no_captions"
  | "video_unavailable"
  | "youtube_blocked"
  | "provider_unavailable"
  | "transcript_fetch_failed"
  | "rate_limited";

/**
 * `POST /api/summary` can return the summary-specific codes below, plus any
 * transcript code when it has to fetch the source transcript first.
 */
export type SummaryErrorDetail = TranscriptErrorDetail | "summary_disabled" | "summary_rate_limited" | "summary_busy" | "summary_failed";

/**
 * The canonical origin, used for `metadataBase`, the sitemap and robots.txt.
 *
 * This used to be copy-pasted into three files, which meant a domain change
 * could silently update two of three. It lives here so there is one place to
 * edit — see docs/operations.md §8.
 */
export const SITE_URL = "https://shrutilipi.nayankunwar.com";

export { friendlyError } from "./errors";

/** Seconds -> `m:ss`, or `h:mm:ss` once the video runs past an hour. */
export function formatTime(s: number): string {
  const total = Math.max(0, Math.floor(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export { toSrt, toVtt } from "./subtitles";
