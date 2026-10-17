"use client";

import { useEffect, useRef, useState } from "react";
import type { ServerWakeStatus } from "../lib/useServerWake";

/**
 * Slim status pill for the free-tier cold-start wake-up.
 *
 * Silent in `checking`; shows "warming" once a ping runs long; after a
 * genuinely slow wake it confirms "ready" for a moment, then fades away.
 */
export default function ServerStatus({
  status,
  onRetry,
}: {
  status: ServerWakeStatus;
  onRetry: () => void;
}) {
  const sawTrouble = useRef(false);
  const [showReady, setShowReady] = useState(false);

  useEffect(() => {
    if (status === "warming" || status === "failed") sawTrouble.current = true;

    if (status !== "ready") {
      setShowReady(false);
      return;
    }
    // Fast pings stay quiet: the "ready" toast is only useful after a wait
    // or a prior failure.
    if (!sawTrouble.current) return;
    setShowReady(true);
    const t = window.setTimeout(() => {
      setShowReady(false);
      sawTrouble.current = false;
    }, 3000);
    return () => window.clearTimeout(t);
  }, [status]);

  if (status === "warming") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
      >
        <SpinnerIcon />
        <span>Waking up the API &mdash; the free tier sleeps when idle. This can take ~30s&hellip;</span>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
      >
        <span>Couldn&rsquo;t reach the API &mdash; it may be starting up.</span>
        <button
          onClick={onRetry}
          className="shrink-0 rounded-lg border border-red-300 px-2.5 py-1 font-medium transition hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-950"
        >
          Try again
        </button>
      </div>
    );
  }

  if (showReady) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
      >
        <CheckIcon />
        <span>API awake &mdash; you&rsquo;re good to go.</span>
      </div>
    );
  }

  return null;
}

function SpinnerIcon() {
  return (
    <svg
      className="animate-spin"
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}
