"use client";

import { useMemo, useState } from "react";
import type { TranscriptResponse } from "../lib/api";

function formatTime(s: number): string {
  const total = Math.max(0, Math.floor(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

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
    <div className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{data.title || data.videoId}</p>
          <p className="text-xs text-zinc-500">
            {data.videoId} · {data.language} · {data.segments.length} segments
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={showTimestamps}
            onChange={(e) => setShowTimestamps(e.target.checked)}
          />
          Timestamps
        </label>
        <button
          onClick={handleCopy}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium hover:bg-zinc-800"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
        <button
          onClick={handleDownload}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium hover:bg-zinc-800"
        >
          Download .txt
        </button>
      </div>

      <div className="max-h-[480px] overflow-y-auto rounded-xl bg-zinc-950 p-4 text-sm leading-relaxed">
        {showTimestamps ? (
          <div className="space-y-1.5">
            {data.segments.map((s, i) => (
              <p key={i}>
                <span className="mr-2 font-mono text-xs text-zinc-500">{formatTime(s.start)}</span>
                <span className="text-zinc-200">{s.text}</span>
              </p>
            ))}
          </div>
        ) : (
          <p className="whitespace-pre-wrap text-zinc-200">{data.plainText}</p>
        )}
      </div>
    </div>
  );
}
