"use client";

import { useMemo, useState } from "react";
import {
  formatTime,
  toSrt,
  toVtt,
  type SummaryResponse,
  type TranscriptResponse,
} from "@shrutilipi/shared";
import { fetchSummary } from "../lib/api";
import ShareButtons from "./ShareButtons";

export default function TranscriptView({ data }: { data: TranscriptResponse }) {
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [copied, setCopied] = useState(false);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);

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

      <div className="max-h-[480px] overflow-y-auto rounded-xl bg-zinc-50 p-4 text-sm leading-relaxed dark:bg-zinc-950">
        {showTimestamps ? (
          <div className="space-y-1.5">
            {data.segments.map((s, i) => (
              <p key={i}>
                <span className="mr-2 font-mono text-xs text-zinc-500">{formatTime(s.start)}</span>
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
