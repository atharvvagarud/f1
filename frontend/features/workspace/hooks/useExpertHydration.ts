// Canonical deep-link hydration for expert surfaces (V3.10G).
//
// Lets /strategy and /counterfactuals consume the canonical pit-wall
// identity (?race=&frame=&driver=, see workspaceUrl.ts) without changing
// any science semantics: race selection, frame selection, and driver
// prefill flow through the surfaces' existing validated callbacks.
// Everything is exact and fail-closed:
//
//   unknown race      -> deep link ignored, surface keeps its own defaults
//   frame out of range -> frame ignored (never clamped), driver still applies
//   malformed query   -> ignored entirely, surface keeps its own defaults
//
// Client-only mount read (window.location.search, mirroring useWorkspace):
// no SSR/Suspense implications. Applies at most once per mount; later
// user interaction always wins. Reload preserves identity because the
// canonical params stay in the URL.

"use client";

import { useEffect, useMemo, useRef } from "react";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { parseWorkspaceSearch } from "../lib/workspaceUrl.ts";
import type { WorkspaceState } from "../lib/workspaceState.ts";

export function useExpertWorkspaceHydration(args: {
  racesLoading: boolean;
  raceIds: readonly string[];
  raceId: string | null;
  totalFrames: number;
  /** Current frame ordinal, or null when unknown. Same-value selections are
   * skipped: re-selecting the current frame would bump the surface session
   * and orphan its in-flight availability work. */
  frameIndex: number | null;
  /** Opaque identity of the current driver selection (view-defined). Same
   * value skips the driver prefill for the same reason. Null always applies. */
  driverKey: string | null;
  selectRace: (raceId: string) => void;
  selectFrame: (frameIndex: number) => void;
  applyDriver: (driverId: string) => void;
}): WorkspaceState | null {
  const deepLink = useMemo<WorkspaceState | null>(() => {
    if (typeof window === "undefined") return null;
    let search: string;
    try {
      search = window.location.search;
    } catch {
      return null;
    }
    if (!search) return null;
    const result = parseWorkspaceSearch(search);
    return result.ok ? result.state : null;
  }, []);
  const appliedRef = useRef(false);
  const deepLinkJson = deepLink ? JSON.stringify(deepLink) : null;

  useEffect(() => {
    if (appliedRef.current || !deepLink) return;
    if (args.racesLoading) return;
    if (!args.raceIds.includes(deepLink.raceId)) {
      // Unknown race: ignore the deep link entirely (fail-closed).
      appliedRef.current = true;
      return;
    }
    if (args.raceId !== deepLink.raceId) {
      args.selectRace(deepLink.raceId);
      return;
    }
    if (args.totalFrames <= 0) return;
    // Exact frame only; out-of-range is dropped, never clamped.
    // Same-value selections are skipped (see frameIndex/driverKey).
    if (deepLink.frameIndex < args.totalFrames && args.frameIndex !== deepLink.frameIndex) {
      args.selectFrame(deepLink.frameIndex);
    }
    if (
      deepLink.selectedDriverId &&
      (args.driverKey === null || args.driverKey !== deepLink.selectedDriverId)
    ) {
      args.applyDriver(deepLink.selectedDriverId);
    }
    appliedRef.current = true;
    // Callbacks are stable surface setters; identity comes from deepLinkJson.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [args.racesLoading, args.raceId, args.totalFrames, deepLinkJson]);

  return deepLink;
}
