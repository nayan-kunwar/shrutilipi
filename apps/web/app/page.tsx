"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import UrlInput from "../components/UrlInput";
import TranscriptView from "../components/TranscriptView";
import ServerStatus from "../components/ServerStatus";
import { fetchTranscript, type TranscriptResponse } from "../lib/api";
import { useServerWake } from "../lib/useServerWake";

function HomeInner() {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("en");
  const [loading, setLoading] = useState(false);
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<TranscriptResponse | null>(null);
  const [dark, setDark] = useState(true);
  const bootstrapped = useRef(false);
  const { status: serverStatus, wake, retry: retryWake } = useServerWake();

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  // Tick while fetching so slow requests can explain the free-tier cold start.
  useEffect(() => {
    if (!loading) return;
    setLoadingSeconds(0);
    const id = window.setInterval(() => setLoadingSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  async function runFetch(urlValue: string, langValue: string) {
    if (!urlValue.trim() || loading) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await fetchTranscript(urlValue.trim(), langValue);
      setData(result);
      try {
        const qs = `?url=${encodeURIComponent(result.videoId)}&lang=${encodeURIComponent(langValue)}`;
        window.history.replaceState(null, "", qs);
      } catch {
        // history API unavailable — shareable link just won't update
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit() {
    wake();
    void runFetch(url, lang);
  }

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    const presetLang = searchParams.get("lang");
    const presetUrl = searchParams.get("url");
    if (presetLang) setLang(presetLang);
    if (presetUrl) {
      setUrl(presetUrl);
      void runFetch(presetUrl, presetLang || "en");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("shrutilipi-theme", next ? "dark" : "light");
    } catch {
      // storage unavailable (private mode) — theme still applies for this session
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-4 px-4 py-10">
      <header className="relative text-center">
        <button
          onClick={toggleTheme}
          aria-label="Toggle light/dark theme"
          className="absolute right-0 top-0 rounded-lg border border-zinc-200 p-2 text-zinc-500 transition hover:border-brand hover:text-brand dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-brand dark:hover:text-brand"
        >
          {dark ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
            </svg>
          )}
        </button>
        <h1 className="text-3xl font-bold tracking-tight">
          Shruti<span className="text-brand">Lipi</span>
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Paste a YouTube URL, get the transcript — copy it, download .txt/.srt/.vtt, or summarize it.
        </p>
      </header>

      <ServerStatus status={serverStatus} onRetry={retryWake} />

      <UrlInput
        url={url}
        lang={lang}
        loading={loading}
        onUrlChange={(v) => {
          setUrl(v);
          wake();
        }}
        onLangChange={setLang}
        onSubmit={handleSubmit}
      />

      {loading && (
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          {loadingSeconds >= 3
            ? "Still working — the free-tier server may be waking up. The first request after idle can take ~30s…"
            : "Fetching captions…"}
        </div>
      )}

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <span>{error}</span>
          {url.trim() && (
            <button
              onClick={handleSubmit}
              className="shrink-0 rounded-lg border border-red-300 px-3 py-1 font-medium transition hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-950"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {data && <TranscriptView key={`${data.videoId}:${data.language}`} data={data} />}
    </main>
  );
}

export default function Home() {
  return (
    <Suspense fallback={null}>
      <HomeInner />
    </Suspense>
  );
}
