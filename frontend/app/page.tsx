"use client";

import { useState } from "react";
import UrlInput from "../components/UrlInput";
import TranscriptView from "../components/TranscriptView";
import { fetchTranscript, type TranscriptResponse } from "../lib/api";

export default function Home() {
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("en");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<TranscriptResponse | null>(null);

  async function handleSubmit() {
    if (!url.trim() || loading) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await fetchTranscript(url.trim(), lang);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-4 px-4 py-10">
      <header className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">ShrutiLipi</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Paste a YouTube URL, get the transcript, copy it.
        </p>
      </header>

      <UrlInput
        url={url}
        lang={lang}
        loading={loading}
        onUrlChange={setUrl}
        onLangChange={setLang}
        onSubmit={handleSubmit}
      />

      {loading && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
          Fetching captions…
        </div>
      )}

      {error && (
        <div className="rounded-2xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {data && <TranscriptView data={data} />}

      <footer className="mt-6 text-center text-xs text-zinc-600">
        Backend: <code>NEXT_PUBLIC_API_URL</code> → FastAPI <code>/api/transcript</code> · v1 captions-only
      </footer>
    </main>
  );
}
