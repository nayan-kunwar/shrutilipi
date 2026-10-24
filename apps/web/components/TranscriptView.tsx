"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  formatTime,
  toSrt,
  toVtt,
  type SummaryResponse,
  type TranscriptResponse,
} from "@shrutilipi/shared";
import { fetchSummary } from "../lib/api";
import ShareButtons from "./ShareButtons";

const YT_ORIGIN = "https://www.youtube.com";
// The handshake id only has to be unique among players on this page; one
// TranscriptView (and therefore one player) is mounted at a time.
const PLAYER_ID = 1;

export default function TranscriptView({ data }: { data: TranscriptResponse }) {
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [copied, setCopied] = useState(false);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);
  const playerRef = useRef<HTMLIFrameElement>(null);
  const playerReadyRef = useRef(false);
  const pendingSeekRef = useRef<number | null>(null);
  const listenTimerRef = useRef<number | null>(null);
  const listenAttemptsRef = useRef(0);

  const textToCopy = useMemo(() => {
    if (!showTimestamps) return data.plainText;
    return data.segments.map((s) => `[${formatTime(s.start)}] ${s.text}`).join("\n");
  }, [data, showTimestamps]);

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for non-secure contexts
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  }

  async function handleCopy() {
    await copyText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleCopySummary() {
    if (!summary) return;
    await copyText(summary.summary);
    setSummaryCopied(true);
    setTimeout(() => setSummaryCopied(false), 2000);
  }

  async function handleGenerateSummary() {
    if (summaryLoading) return;
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      setSummary(await fetchSummary(data.videoId, data.language));
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Couldn't generate a summary.");
    } finally {
      setSummaryLoading(false);
    }
  }

  const postToPlayer = useCallback((message: unknown) => {
    playerRef.current?.contentWindow?.postMessage(JSON.stringify(message), YT_ORIGIN);
  }, []);

  const sendPlayerCommand = useCallback(
    (func: string, args: unknown[] = []) => {
      postToPlayer({ event: "command", func, args, id: PLAYER_ID });
    },
    [postToPlayer]
  );

  const stopListening = useCallback(() => {
    if (listenTimerRef.current !== null) {
      window.clearInterval(listenTimerRef.current);
      listenTimerRef.current = null;
    }
  }, []);

  /**
   * Shake hands with the embed so we know when it can accept commands.
   *
   * YouTube only starts reporting readiness after the parent sends a
   * `listening` message (the same handshake its IFrame API script performs).
   * Until `onReady` arrives, a `seekTo` can be silently dropped, which is easy
   * to hit on a cold embed: click a timestamp as soon as the transcript
   * renders and the player is still booting. Ping until ready, then stop.
   */
  const startListening = useCallback(() => {
    playerReadyRef.current = false;
    stopListening();
    listenAttemptsRef.current = 0;
    const ping = () => {
      listenAttemptsRef.current += 1;
      // Give up after ~60 s; direct commands remain best-effort thereafter.
      if (listenAttemptsRef.current > 240) {
        stopListening();
        return;
      }
      postToPlayer({ event: "listening", id: PLAYER_ID });
    };
    ping();
    listenTimerRef.current = window.setInterval(ping, 250);
  }, [postToPlayer, stopListening]);

  useEffect(() => {
    function onPlayerMessage(event: MessageEvent) {
      if (event.origin !== YT_ORIGIN) return;
      if (event.source !== playerRef.current?.contentWindow) return;
      let message: { event?: string } | null = null;
      try {
        message = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
      } catch {
        return;
      }
      if (message?.event !== "onReady") return;
      playerReadyRef.current = true;
      stopListening();
      const pending = pendingSeekRef.current;
      if (pending !== null) {
        pendingSeekRef.current = null;
        sendPlayerCommand("seekTo", [pending, true]);
        sendPlayerCommand("playVideo");
      }
    }

    window.addEventListener("message", onPlayerMessage);
    startListening();
    return () => {
      window.removeEventListener("message", onPlayerMessage);
      stopListening();
    };
  }, [sendPlayerCommand, startListening, stopListening]);

  /**
   * Seek the embedded player via YouTube's postMessage command API.
   *
   * No external SDK is loaded, so there is no third-party script or CSP
   * exception to maintain. A target clicked before the embed is ready is
   * queued and applied on `onReady`; the immediate send is a fallback for the
   * case where the handshake never completes but the player is nevertheless
   * accepting commands. `playVideo` runs in the same click gesture, so
   * autoplay policies allow it.
   */
  function seekTo(seconds: number) {
    if (!playerReadyRef.current) pendingSeekRef.current = seconds;
    sendPlayerCommand("seekTo", [seconds, true]);
    sendPlayerCommand("playVideo");
  }

  function downloadFile(name: string, content: string, mime: string) {
    const blob = new Blob([content], { type: mime });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // .txt honors the Timestamps checkbox; the subtitle formats always carry
  // timestamps by nature, so they ignore it.
  function handleDownload(fmt: "txt" | "srt" | "vtt") {
    const content =
      fmt === "txt" ? textToCopy : fmt === "srt" ? toSrt(data.segments) : toVtt(data.segments);
    const mime =
      fmt === "txt"
        ? "text/plain;charset=utf-8"
        : fmt === "srt"
          ? "application/x-subrip;charset=utf-8"
          : "text/vtt;charset=utf-8";
    downloadFile(`${data.videoId}.${fmt}`, content, mime);
  }

  return (
    <div className="w-full rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{data.title || data.videoId}</p>
          <p className="text-xs text-zinc-500">
            {data.videoId} · {data.language} · {data.segments.length} segments
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          <input
            type="checkbox"
            checked={showTimestamps}
            onChange={(e) => setShowTimestamps(e.target.checked)}
            className="accent-brand"
          />
          Timestamps
        </label>
        <button
          onClick={handleCopy}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium transition hover:border-brand hover:text-brand dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-brand dark:hover:text-brand"
        >
          {copied ? <span className="text-brand">Copied ✓</span> : "Copy"}
        </button>
        <div
          className="flex items-stretch overflow-hidden rounded-lg border border-zinc-300 dark:border-zinc-700"
          role="group"
          aria-label="Download transcript"
        >
          <span className="flex items-center px-2 text-xs text-zinc-500 dark:text-zinc-400">
            Download
          </span>
          {(["txt", "srt", "vtt"] as const).map((fmt, i) => (
            <button
              key={fmt}
              onClick={() => handleDownload(fmt)}
              title={`Download ${data.videoId}.${fmt}`}
              className={`px-2.5 py-1.5 text-xs font-medium transition hover:bg-zinc-100 hover:text-brand dark:hover:bg-zinc-800 ${
                i > 0 ? "border-l border-zinc-300 dark:border-zinc-700" : ""
              }`}
            >
              .{fmt}
            </button>
          ))}
        </div>
        <ShareButtons videoId={data.videoId} lang={data.language} title={data.title || data.videoId} />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2" aria-live="polite">
        <button
          onClick={handleGenerateSummary}
          disabled={summaryLoading}
          aria-busy={summaryLoading}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-brand dark:hover:text-brand"
        >
          {summaryLoading
            ? "Generating summary…"
            : summary
              ? "Refresh summary"
              : "Generate summary"}
        </button>
        {summaryError && (
          <span role="alert" className="text-xs text-red-600 dark:text-red-300">
            {summaryError}
          </span>
        )}
      </div>

      {summary && (
        <div className="mb-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Summary</p>
            <button
              onClick={handleCopySummary}
              className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium transition hover:border-brand hover:text-brand dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-brand dark:hover:text-brand"
            >
              {summaryCopied ? <span className="text-brand">Copied ✓</span> : "Copy summary"}
            </button>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-800 dark:text-zinc-200">
            {summary.summary}
          </p>
          <p className="mt-2 text-[11px] text-zinc-400 dark:text-zinc-500">
            Generated on demand · cached for 24 h
          </p>
        </div>
      )}

      <div className="mb-3 aspect-video overflow-hidden rounded-xl border border-zinc-200 bg-black dark:border-zinc-800">
        <iframe
          ref={playerRef}
          src={`https://www.youtube.com/embed/${data.videoId}?enablejsapi=1&playsinline=1&rel=0`}
          title={data.title ? `Video: ${data.title}` : `YouTube video ${data.videoId}`}
          className="h-full w-full border-0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          referrerPolicy="strict-origin-when-cross-origin"
          allowFullScreen
        />
      </div>

      <div className="max-h-[480px] overflow-y-auto rounded-xl bg-zinc-50 p-4 text-sm leading-relaxed dark:bg-zinc-950">
        {showTimestamps ? (
          <div className="space-y-1.5">
            <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
              Click a timestamp to jump to that moment.
            </p>
            {data.segments.map((s, i) => (
              <p key={i}>
                <button
                  type="button"
                  onClick={() => seekTo(s.start)}
                  aria-label={`Seek to ${formatTime(s.start)}`}
                  title={`Seek to ${formatTime(s.start)}`}
                  className="mr-2 rounded font-mono text-xs text-zinc-500 underline-offset-2 transition hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand dark:text-zinc-400"
                >
                  {formatTime(s.start)}
                </button>
                <span className="text-zinc-800 dark:text-zinc-200">{s.text}</span>
              </p>
            ))}
          </div>
        ) : (
          <p className="whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">{data.plainText}</p>
        )}
      </div>
    </div>
  );
}
