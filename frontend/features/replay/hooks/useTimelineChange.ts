// On-demand E5 prediction-change fetch (Phase-8 E5).
//
// Fetched only when a checkpoint + driver is explicitly selected; exactly one
// request per (race, frame, driver) selection with AbortController stale
// protection. Product states travel in the 200 body (AVAILABLE /
// NO_PREVIOUS_CHECKPOINT / COMPARISON_UNAVAILABLE); a 503 cache absence is an
// explicit, non-fatal technical state, never retried in a loop.
//
// The resolved payload is stored with the selection key that produced it, so a
// late response for a superseded driver/frame can never render under the new
// selection (the hook reports LOADING until the matching payload arrives).

"use client";

import { useEffect, useState } from "react";
import {
  V2ApiError,
  getReplayPredictionChange,
  type TimelineChangeResponse,
} from "@/lib/v2";
import {
  explanationSelectionKey,
  resolvedSelection,
  type SelectionKeyed,
} from "@/features/replay/lib/explanationSelection";

export type TimelineChangeView =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; change: TimelineChangeResponse }
  | { kind: "no_previous" }
  | { kind: "comparison_unavailable"; reason: string | null }
  | { kind: "unavailable"; reason: string | null }
  | { kind: "error"; message: string };

const LOADING: TimelineChangeView = { kind: "loading" };
const IDLE: TimelineChangeView = { kind: "idle" };

export function useTimelineChange(
  raceId: string,
  frameIndex: number,
  driverId: string | null,
): TimelineChangeView {
  const [state, setState] = useState<SelectionKeyed<TimelineChangeView> | null>(
    null,
  );

  useEffect(() => {
    if (driverId === null) return;
    const key = explanationSelectionKey(raceId, frameIndex, driverId);
    const controller = new AbortController();
    let cancelled = false;
    getReplayPredictionChange(
      raceId,
      frameIndex,
      driverId,
      fetch,
      undefined,
      controller.signal,
    )
      .then((change) => {
        if (cancelled) return;
        if (change.status === "NO_PREVIOUS_CHECKPOINT") {
          setState({ key, view: { kind: "no_previous" } });
        } else if (change.status === "COMPARISON_UNAVAILABLE") {
          setState({
            key,
            view: { kind: "comparison_unavailable", reason: change.reason },
          });
        } else {
          setState({ key, view: { kind: "ready", change } });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        let view: TimelineChangeView;
        if (error instanceof V2ApiError && error.isUnavailable()) {
          view = { kind: "unavailable", reason: error.reason };
        } else if (error instanceof V2ApiError) {
          view = {
            kind: "error",
            message: `Model score change unavailable (${error.status} ${error.code}).`,
          };
        } else {
          view = { kind: "error", message: "Model score change request failed." };
        }
        setState({ key, view });
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [raceId, frameIndex, driverId]);

  if (driverId === null) return IDLE;
  return resolvedSelection(
    state,
    explanationSelectionKey(raceId, frameIndex, driverId),
    LOADING,
  );
}
