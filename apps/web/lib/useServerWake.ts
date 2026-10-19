"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { pingHealth } from "./api";

export type ServerWakeStatus = "checking" | "warming" | "ready" | "failed";

/** A ping still pending after this long means a cold start is in progress (~30s). */
const WARMING_AFTER_MS = 2500;
/** Render free instances sleep after ~15 min idle; keep-warm below that. */
const KEEP_WARM_INTERVAL_MS = 10 * 60 * 1000;
/** Interactions and tab-returns only re-ping if the last ping is this old. */
const REPING_AFTER_MS = 5 * 60 * 1000;

/**
 * Wakes the Render free-tier API and reports its state.
 *
 * Three triggers, all against /api/wake (no upstream quota, no rate-limit
 * tokens): page load, so the boot starts while the user is still pasting a
 * URL; tab return or first interaction, if the last ping is stale; and a
 * visible-tab keep-warm interval that stays under Render's sleep timer.
 */
export function useServerWake() {
  const [status, setStatus] = useState<ServerWakeStatus>("checking");
  const inFlight = useRef(false);
  const lastPingAt = useRef(0);
  const statusRef = useRef<ServerWakeStatus>("checking");

  const set = useCallback((next: ServerWakeStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  /** `visible` pings drive the status pill; keep-warm pings stay silent. */
  const ping = useCallback(
    async (visible: boolean) => {
      if (inFlight.current) return;
      inFlight.current = true;
      lastPingAt.current = Date.now();

      let timer: number | undefined;
      if (visible) {
        timer = window.setTimeout(() => {
          set(statusRef.current === "checking" ? "warming" : statusRef.current);
        }, WARMING_AFTER_MS);
      }

      const ok = await pingHealth();
      if (visible) set(ok ? "ready" : "failed");

      if (timer !== undefined) window.clearTimeout(timer);
      inFlight.current = false;
    },
    [set]
  );

  const kick = useCallback(
    (force = false) => {
      if (inFlight.current) return;
      const stale = Date.now() - lastPingAt.current >= REPING_AFTER_MS;
      if (!force && !stale && statusRef.current !== "failed") return;
      set("checking");
      void ping(true);
    },
    [ping, set]
  );

  /** Page load: start the boot immediately. */
  useEffect(() => {
    void ping(true);
  }, [ping]);

  /** Keep a visible tab's instance warm (hidden tabs can't wake it anyway). */
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void ping(false);
    }, KEEP_WARM_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [ping]);

  /** Returning to the tab may mean the instance slept while it was hidden. */
  useEffect(() => {
    function onVisibility() {
      if (document.visibilityState === "visible") kick();
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [kick]);

  /** First user interaction: cheap insurance if the machine slept under us. */
  const wake = useCallback(() => kick(), [kick]);

  /** Retry button: bypass the dedupe/time guards. */
  const retry = useCallback(() => {
    if (inFlight.current) return;
    set("checking");
    void ping(true);
  }, [ping, set]);

  return { status, wake, retry };
}
