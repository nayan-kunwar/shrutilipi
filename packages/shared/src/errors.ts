/**
 * Map an HTTP status + backend `detail` code to a sentence worth showing a user.
 * Unknown codes fall back to the raw detail so a new backend code is visible in
 * the UI rather than swallowed.
 *
 * This lives in its own module (re-exported from the package index) so the
 * Node test runner can import it directly — Node ESM resolves relative imports
 * literally, without TypeScript's extension inference.
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
    case "rate_limited":
      return "You're requesting transcripts a bit too quickly — wait a minute and retry.";
    case "summary_disabled":
      return "Summary generation isn't configured on this deployment.";
    case "summary_rate_limited":
      return "You've generated a lot of summaries — wait a minute and retry.";
    case "summary_busy":
      return "A summary for this video is already being generated — retry in a moment.";
    case "summary_failed":
      return "Couldn't generate a summary. The transcript is unaffected — retry in a moment.";
    default:
      return status === 404 ? "Transcript not found for this video." : detail;
  }
}
