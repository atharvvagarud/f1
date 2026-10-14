// Driver-telemetry corpus hook (V3.10F).
//
// Per-race follower (mount with key={raceId}, like usePitWallRace): exactly
// ONE read-only request serves the whole race's lap + stint evidence,
// adapted once and cached module-level per race. Driver switches re-slice
// locally via the pure causal selectors — zero new requests. No per-frame
// fetch, no science endpoints, no prediction/probability reads.
//
// Honesty rules: the corpus is valid only when the single response loads
// intact (race identity must match). Failures surface as "unavailable"
// with retry — never as partial telemetry, never as zeros.

"use client";

import { useEffect, useRef, useState } from "react";
import { getRaceTelemetry } from "@/lib/v2";
import {
  adaptTelemetryResponse,
  type TelemetryCorpus,
} from "@/features/pit-wall/lib/telemetry";

export type TelemetryStatus = "loading" | "ready" | "unavailable";

// Module-level corpus cache: one entry per race, shared across mounts.
const corpusCache = new Map<string, TelemetryCorpus>();

/** Test seam: clear the module cache (tests only). */
export function clearTelemetryCacheForTests(): void {
  corpusCache.clear();
}

export function useDriverTelemetry(raceId: string) {
  const [fetchedCorpus, setFetchedCorpus] = useState<TelemetryCorpus | null>(
    null,
  );
  const [fetchedStatus, setFetchedStatus] =
    useState<TelemetryStatus>("loading");
  const [retryNonce, setRetryNonce] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // The module cache is read during render: a warm entry resolves with
  // zero effects and zero fetches. The fetch effect below only runs for
  // cold races, keeping every setState inside async continuations.
  const warm = corpusCache.get(raceId);
  const corpus = warm ?? fetchedCorpus;
  const status: TelemetryStatus = warm ? "ready" : fetchedStatus;

  useEffect(() => {
    if (warm) return;
    const controller = new AbortController();
    let cancelled = false;
    getRaceTelemetry(raceId, fetch, undefined, controller.signal)
      .then((body) => {
        if (cancelled || !mountedRef.current) return;
        if (body.race_id !== raceId) {
          throw new Error(
            `Telemetry identity break: requested ${raceId}, got ${body.race_id}.`,
          );
        }
        const adapted = adaptTelemetryResponse(body);
        corpusCache.set(raceId, adapted);
        setFetchedCorpus(adapted);
        setFetchedStatus("ready");
      })
      .catch((error) => {
        if (cancelled || !mountedRef.current) return;
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setFetchedStatus("unavailable");
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [raceId, retryNonce, warm]);

  const retry = (): void => {
    corpusCache.delete(raceId);
    setFetchedCorpus(null);
    setFetchedStatus("loading");
    setRetryNonce((n) => n + 1);
  };

  return { status, corpus, retry };
}

export type DriverTelemetry = ReturnType<typeof useDriverTelemetry>;
