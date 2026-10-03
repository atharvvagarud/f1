// Spatial track lifecycle for the historical replay (Phase-12 P12-7).
//
// Follows the single existing replay position: the caller passes the exact
// current (raceId, frameIndex, anchorStateTimeS) owned by useReplay. This
// hook never derives an index from lap/time/slider and owns no playback
// clock. Geometry is race-scoped (fetched once per race, then reused);
// frames are fetched per currentFrameIndex with AbortController +
// generation-ticket guards so out-of-order arrivals can never regress the
// UI and a late race-A response can never render on race B.
//
// Admission predicates live in ../lib/spatialIntegration (node-tested);
// this hook owns fetch/abort/state only. No trail fetching (deferred per
// P12-7 evidence-first decision), no prefetch, no debounce: playback
// already advances after each response, and scrub seeks abort in flight.
//
// State shape (lint-clean under react-hooks v7): caches are render state
// (read during render, written only inside async fetch callbacks); effects
// only synchronize with the network. No setState runs synchronously in an
// effect body and no ref is read during render.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getSpatialFrame,
  getSpatialGeometry,
  type SpatialFrame,
  type SpatialGeometry,
} from "@/lib/spatial";
import {
  classifySpatialFailure,
  createSpatialRequestTracker,
  isSpatialClockConsistent,
  isSpatialResponseCurrent,
  spatialFrameCacheKey,
} from "@/features/replay/lib/spatialIntegration";

const FRAME_CACHE_LIMIT = 200;

export type SpatialPanelState =
  | "idle"
  | "loading"
  | "ready"
  | "unavailable"
  | "error";

export type SpatialTrackState = {
  geometry: SpatialGeometry | null;
  geometryStatus: SpatialPanelState;
  /** Authoritative frame: matches current race + index + replay clock. */
  frame: SpatialFrame | null;
  frameStatus: SpatialPanelState;
  /** Last authoritative frame for the CURRENT race (any index). */
  displayFrame: SpatialFrame | null;
  /** True while the current index has no authoritative frame yet. */
  isFramePending: boolean;
  errorDetail: string | null;
  retry: () => void;
};

type GeometryError = { raceId: string; detail: string };
type FrameError = { raceId: string; frameIndex: number; detail: string };
type FrameUnavailable = { raceId: string; frameIndex: number };

function errorDetailFor(code: string | null, scope: string): string {
  if (code === "spatial_integrity_error") {
    return `${scope} failed integrity checks. Markers withheld.`;
  }
  if (code === "unknown_race") {
    return `Race is not served with spatial state (${scope}).`;
  }
  if (code === "unknown_frame") {
    return `Frame is not in this race's spatial timeline (${scope}).`;
  }
  return `${scope} request failed. Retry navigation or the panel retry.`;
}

function errorDetailOf(err: unknown, scope: string): string {
  const code =
    err !== null && typeof err === "object" && "code" in err
      ? String((err as { code: unknown }).code ?? "")
      : null;
  return errorDetailFor(code || null, scope);
}

/** Bounded insert into a keyed record (insertion-ordered, oldest evicted). */
function withBoundedEntry<T>(
  prev: Record<string, T>,
  key: string,
  value: T,
  limit: number,
): Record<string, T> {
  if (key in prev) return { ...prev, [key]: value };
  const keys = Object.keys(prev);
  if (keys.length < limit) return { ...prev, [key]: value };
  const next: Record<string, T> = {};
  for (const k of keys.slice(keys.length - limit + 1)) next[k] = prev[k];
  next[key] = value;
  return next;
}

export function useSpatialTrack(args: {
  raceId: string | null;
  frameIndex: number;
  anchorStateTimeS: number | null;
}): SpatialTrackState {
  const { raceId, frameIndex, anchorStateTimeS } = args;

  // Render-visible caches: written only inside fetch callbacks below.
  const [geometryCache, setGeometryCache] = useState<
    Record<string, SpatialGeometry>
  >({});
  const [geometryUnavailable, setGeometryUnavailable] = useState<
    Record<string, true>
  >({});
  const [geometryError, setGeometryError] = useState<GeometryError | null>(
    null,
  );
  const [frameCache, setFrameCache] = useState<Record<string, SpatialFrame>>(
    {},
  );
  const [frameUnavailable, setFrameUnavailable] =
    useState<FrameUnavailable | null>(null);
  const [frameError, setFrameError] = useState<FrameError | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);

  // Network-only refs: touched in effects / async callbacks, never read
  // during render.
  const geometryGenerationRef = useRef(0);
  const geometryAbortRef = useRef<AbortController | null>(null);
  const trackerRef = useRef(createSpatialRequestTracker());
  const frameAbortRef = useRef<AbortController | null>(null);
  const liveRef = useRef<{ raceId: string | null; frameIndex: number }>({
    raceId: null,
    frameIndex: 0,
  });

  const retry = useCallback(() => setRetryNonce((n) => n + 1), []);

  const geometryCached = raceId !== null && raceId in geometryCache;
  const geometryIsUnavailable =
    raceId !== null && raceId in geometryUnavailable;

  // --- geometry: one fetch per race, reused across all frame changes ---
  useEffect(() => {
    if (raceId === null) {
      geometryAbortRef.current?.abort();
      return;
    }
    if (geometryCached || geometryIsUnavailable) return;
    const generation = ++geometryGenerationRef.current;
    geometryAbortRef.current?.abort();
    const controller = new AbortController();
    geometryAbortRef.current = controller;
    let cancelled = false;
    getSpatialGeometry(raceId, fetch, undefined, controller.signal)
      .then((response) => {
        if (cancelled || geometryGenerationRef.current !== generation) return;
        if (response.race_id !== raceId) {
          // Identity failure: never cache, never render cross-race geometry.
          setGeometryError({
            raceId,
            detail: "Geometry identity does not match the current race.",
          });
          return;
        }
        setGeometryCache((prev) => ({ ...prev, [raceId]: response }));
      })
      .catch((err: unknown) => {
        if (cancelled || geometryGenerationRef.current !== generation) return;
        const kind = classifySpatialFailure(err);
        if (kind === "aborted") return;
        if (kind === "unavailable") {
          setGeometryUnavailable((prev) => ({ ...prev, [raceId]: true }));
          return;
        }
        setGeometryError({
          raceId,
          detail: errorDetailOf(err, "Geometry"),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [raceId, retryNonce, geometryCached, geometryIsUnavailable]);

  const frameKey =
    raceId !== null ? spatialFrameCacheKey(raceId, frameIndex) : null;
  const frameHit =
    frameKey !== null && anchorStateTimeS !== null
      ? (frameCache[frameKey] ?? null)
      : null;
  const frameHitReady =
    frameHit !== null &&
    anchorStateTimeS !== null &&
    isSpatialClockConsistent(anchorStateTimeS, frameHit);

  // --- frame: exact currentFrameIndex for the current race ---
  useEffect(() => {
    liveRef.current = { raceId, frameIndex };
    if (raceId === null || anchorStateTimeS === null) {
      frameAbortRef.current?.abort();
      return;
    }
    // Cache hit with a consistent clock needs no fetch; render derives
    // the frame and the pending fallback straight from frameCache.
    if (frameHitReady) return;
    const ticket = trackerRef.current.issue(raceId, frameIndex);
    frameAbortRef.current?.abort();
    const controller = new AbortController();
    frameAbortRef.current = controller;
    const wantedAnchor = anchorStateTimeS;
    const wantedKey = spatialFrameCacheKey(raceId, frameIndex);
    let cancelled = false;
    getSpatialFrame(raceId, frameIndex, fetch, undefined, controller.signal)
      .then((response) => {
        if (cancelled || !trackerRef.current.isCurrent(ticket)) return;
        const live = liveRef.current;
        if (
          ticket.raceId !== live.raceId ||
          ticket.frameIndex !== live.frameIndex
        ) {
          return;
        }
        if (
          !isSpatialResponseCurrent(response, ticket.raceId, ticket.frameIndex)
        ) {
          setFrameError({
            raceId: ticket.raceId,
            frameIndex: ticket.frameIndex,
            detail: "Spatial frame identity does not match the replay frame.",
          });
          return;
        }
        if (!isSpatialClockConsistent(wantedAnchor, response)) {
          // Clock disagreement is an integrity failure, never rendered and
          // never cached (no poisoned entries).
          setFrameError({
            raceId: ticket.raceId,
            frameIndex: ticket.frameIndex,
            detail:
              "Spatial clock does not match the replay frame. Markers withheld.",
          });
          return;
        }
        setFrameCache((prev) =>
          withBoundedEntry(prev, wantedKey, response, FRAME_CACHE_LIMIT),
        );
      })
      .catch((err: unknown) => {
        if (cancelled || !trackerRef.current.isCurrent(ticket)) return;
        const live = liveRef.current;
        if (
          ticket.raceId !== live.raceId ||
          ticket.frameIndex !== live.frameIndex
        ) {
          return;
        }
        const kind = classifySpatialFailure(err);
        if (kind === "aborted") return;
        if (kind === "unavailable") {
          setFrameUnavailable({
            raceId: ticket.raceId,
            frameIndex: ticket.frameIndex,
          });
          return;
        }
        setFrameError({
          raceId: ticket.raceId,
          frameIndex: ticket.frameIndex,
          detail: errorDetailOf(err, "Spatial frame"),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [raceId, frameIndex, anchorStateTimeS, retryNonce, frameHitReady]);

  // --- synchronous derivation (render only, race-tagged or idle) ---
  let geometry: SpatialGeometry | null = null;
  let geometryStatus: SpatialPanelState =
    raceId === null ? "idle" : "loading";
  let geometryDetail: string | null = null;
  if (raceId !== null) {
    const cached = geometryCache[raceId] ?? null;
    if (cached) {
      geometry = cached;
      geometryStatus = "ready";
    } else if (raceId in geometryUnavailable) {
      geometryStatus = "unavailable";
    } else if (geometryError !== null && geometryError.raceId === raceId) {
      geometryStatus = "error";
      geometryDetail = geometryError.detail;
    }
  }

  let frame: SpatialFrame | null = null;
  let frameStatus: SpatialPanelState =
    raceId === null || anchorStateTimeS === null ? "idle" : "loading";
  let frameDetail: string | null = null;
  if (raceId !== null && anchorStateTimeS !== null) {
    if (frameHitReady && frameHit !== null) {
      frame = frameHit;
      frameStatus = "ready";
    } else if (
      frameUnavailable !== null &&
      frameUnavailable.raceId === raceId &&
      frameUnavailable.frameIndex === frameIndex
    ) {
      frameStatus = "unavailable";
    } else if (
      frameError !== null &&
      frameError.raceId === raceId &&
      frameError.frameIndex === frameIndex
    ) {
      frameStatus = "error";
      frameDetail = frameError.detail;
    }
  }

  // Last authoritative frame for THIS race only: race A data never renders
  // on race B, even while race B is still loading. Any cached frame for the
  // race counts (highest cached index wins the pending cue).
  let displayFrame: SpatialFrame | null = null;
  if (raceId !== null) {
    if (frame !== null) {
      displayFrame = frame;
    } else {
      let best: SpatialFrame | null = null;
      const prefix = `${raceId}|`;
      for (const key of Object.keys(frameCache)) {
        if (!key.startsWith(prefix)) continue;
        const candidate = frameCache[key];
        if (candidate.race_id !== raceId) continue;
        if (best === null || candidate.frame_index > best.frame_index) {
          best = candidate;
        }
      }
      displayFrame = best;
    }
  }

  const isFramePending =
    frameStatus === "loading" &&
    displayFrame !== null &&
    displayFrame.race_id === raceId;

  return {
    geometry,
    geometryStatus,
    frame,
    frameStatus,
    displayFrame,
    isFramePending,
    errorDetail: geometryDetail ?? frameDetail,
    retry,
  };
}
