"use client";

import { useMemo, useState } from "react";
import { formatTime, type TranscriptResponse } from "@shrutilipi/shared";
import ShareButtons from "./ShareButtons";

export default function TranscriptView({ data }: { data: TranscriptResponse }) {
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [copied, setCopied] = useState(false);

  const textToCopy = useMemo(() => {
    if (!showTimestamps) return data.plainText;
    return data.segments.map((s) => `[${formatTime(s.start)}] ${s.text}`).join("\n");
  }, [data, showTimestamps]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(textToCopy);
    } catch {
      // Fallback for non-secure contexts
      const ta = document.createElement("textarea");
      ta.value = textToCopy;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownload() {
    const blob = new Blob([textToCopy], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${data.videoId}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
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
        <button
          onClick={handleDownload}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium transition hover:border-brand hover:text-brand dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-brand dark:hover:text-brand"
        >
          Download .txt
        </button>
        <ShareButtons videoId={data.videoId} lang={data.language} title={data.title || data.videoId} />
      </div>

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
