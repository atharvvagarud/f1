// Selected-driver intelligence hook (V3.10E).
//
// One frozen V3.9C uncertainty bundle per exact historical anchor
// (race + lap + state time): cheap availability first, at most one compare
// per anchor, session/abort guards against stale responses. The bundle serves
// every driver — switching drivers slices locally and issues no request.
// Read-only historical evidence; no models run, no simulations run.
//
// Identity comes from the caller (the workspace frame); this hook owns only
// the bundle fetch for that anchor. Render-phase cache reads keep every
// setState inside async continuations or event handlers.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getUncertaintyAvailability,
  isUncertaintyUnsupported,
  postUncertaintyCompare,
  type UncertaintyAvailability,
  type UncertaintyCompare,
} from "@/features/uncertainty/lib/uncertaintyClient";
import { V2ApiError } from "@/lib/v2";

export type IntelligenceView =
  | { kind: "loading" }
  | { kind: "ready"; compare: UncertaintyCompare }
  | {
      kind: "not-comparable";
      availability: UncertaintyAvailability;
    }
  | { kind: "unsupported"; reason: string | null }
  | { kind: "error" };

export interface IntelligenceAnchor {
  raceId: string;
  anchorLapNumber: number;
  anchorStateTimeS: number | null;
}

function cacheKey(anchor: IntelligenceAnchor): string {
  return `${anchor.raceId}|${anchor.anchorLapNumber}|${anchor.anchorStateTimeS ?? "-"}`;
}

// Module-level bundle cache: one entry per anchor, shared across mounts.
const bundleCache = new Map<string, IntelligenceView>();

export function useDriverIntelligence(anchor: IntelligenceAnchor | null) {
  const [fetched, setFetched] = useState<IntelligenceView>({ kind: "loading" });
  const [retryNonce, setRetryNonce] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const key = anchor ? cacheKey(anchor) : null;
  const warm = key ? bundleCache.get(key) : undefined;
  const view: IntelligenceView = warm ?? fetched;

  const anchorRaceId = anchor?.raceId ?? null;
  const anchorLap = anchor?.anchorLapNumber ?? null;
  const anchorTime = anchor?.anchorStateTimeS ?? null;

  useEffect(() => {
    if (
      anchorRaceId === null ||
      anchorLap === null ||
      !key ||
      warm
    ) {
      return;
    }
    const request = {
      race_id: anchorRaceId,
      anchor_lap_number: anchorLap,
      anchor_state_time_s: anchorTime,
    };
    let cancelled = false;
    const controller = new AbortController();
    const signal = controller.signal;
    (async (): Promise<void> => {
      try {
        const availability = await getUncertaintyAvailability(
          request,
          fetch,
          undefined,
          signal,
        );
        if (cancelled || !mountedRef.current) return;
        if (availability.comparison !== "COMPARABLE") {
          const next: IntelligenceView = {
            kind: "not-comparable",
            availability,
          };
          bundleCache.set(key, next);
          setFetched(next);
          return;
        }
        const compare = await postUncertaintyCompare(
          request,
          fetch,
          undefined,
          signal,
        );
        if (cancelled || !mountedRef.current) return;
        const next: IntelligenceView = { kind: "ready", compare };
        bundleCache.set(key, next);
        setFetched(next);
      } catch (error: unknown) {
        if (cancelled || !mountedRef.current) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (isUncertaintyUnsupported(error)) {
          const next: IntelligenceView = {
            kind: "unsupported",
            reason: (error as V2ApiError).reason,
          };
          bundleCache.set(key, next);
          setFetched(next);
          return;
        }
        setFetched({ kind: "error" });
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [anchorRaceId, anchorLap, anchorTime, key, warm, retryNonce]);

  const retry = useCallback((): void => {
    if (key) bundleCache.delete(key);
    setFetched({ kind: "loading" });
    setRetryNonce((n) => n + 1);
  }, [key]);

  return { view, retry };
}

export type DriverIntelligenceView = ReturnType<typeof useDriverIntelligence>;
