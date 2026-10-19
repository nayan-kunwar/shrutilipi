/**
 * Subtitle exports — `toSrt` / `toVtt`.
 *
 * Pure formatting from the API's `segments[]`: no environment, no network.
 * Two-language pair: the Python twins are `render_srt()` / `render_vtt()` in
 * tools/fetch.py. Keep the edge-case rules in sync — round ms once, clamp
 * zero-length cues to +1 ms, skip empty text, contiguous numbering, and end
 * every file with a single trailing newline.
 */
import type { TranscriptSegment } from "./index";

/** `HH:MM:SS,mmm` (SRT) or `HH:MM:SS.mmm` (VTT); hours always 2 digits. */
function cueTime(ms: number, sep: "," | "."): string {
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const p2 = (n: number) => String(n).padStart(2, "0");
  return `${p2(h)}:${p2(m)}:${p2(s)}${sep}${String(ms % 1000).padStart(3, "0")}`;
}

/** The cue body shared by both formats; the decimal separator is the only difference. */
function cues(segments: TranscriptSegment[], sep: "," | "."): string {
  const blocks: string[] = [];
  let n = 0;
  for (const seg of segments) {
    if (!seg.text.trim()) continue; // no stray empty cue boxes
    n += 1;
    const startMs = Math.max(0, Math.round(seg.start * 1000));
    // Some players drop zero-length cues; clamp every cue to at least 1 ms.
    const endMs = Math.max(Math.round((seg.start + seg.duration) * 1000), startMs + 1);
    blocks.push(`${n}\n${cueTime(startMs, sep)} --> ${cueTime(endMs, sep)}\n${seg.text}`);
  }
  return blocks.join("\n\n");
}

/** SubRip: numbered cues, comma decimals, no header. */
export function toSrt(segments: TranscriptSegment[]): string {
  const body = cues(segments, ",");
  return body ? `${body}\n` : "";
}

/** WebVTT: `WEBVTT` header plus the same cues with dot decimals. */
export function toVtt(segments: TranscriptSegment[]): string {
  const body = cues(segments, ".");
  return body ? `WEBVTT\n\n${body}\n` : "WEBVTT\n";
}
