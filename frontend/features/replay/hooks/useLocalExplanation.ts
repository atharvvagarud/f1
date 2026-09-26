// On-demand E4 local explanation fetch (Phase-8 E4).
//
// Fetched only when a checkpoint driver row is explicitly expanded; exactly
// one request per (race, frame, driver) selection with AbortController stale
// protection. A 503 cache absence and a 422 non-observable driver are
// explicit, non-fatal technical states, never retried in a loop.
//
// The resolved payload is stored together with the selection key that
// produced it. A payload whose key no longer matches the current selection is
// never rendered: the hook reports LOADING instead of leaking the previous
// selection's explanation under a new race/frame/driver identity.

"use client";

import { useEffect, useState } from "react";
import {
  V2ApiError,
  getReplayExplanation,
  type LocalExplanationResponse,
} from "@/lib/v2";
import {
  explanationSelectionKey,
  resolvedSelection,
  type SelectionKeyed,
} from "@/features/replay/lib/explanationSelection";

export type LocalExplanationView =
  | { kind: "loading" }
  | { kind: "ready"; explanation: LocalExplanationResponse }
  | { kind: "unavailable"; reason: string | null }
  | { kind: "not_observable" }
  | { kind: "error"; message: string };

const LOADING: LocalExplanationView = { kind: "loading" };

export function useLocalExplanation(
  raceId: string,
  frameIndex: number,
  driverId: string,
): LocalExplanationView {
  const [state, setState] = useState<SelectionKeyed<LocalExplanationView> | null>(
    null,
  );

  useEffect(() => {
    const key = explanationSelectionKey(raceId, frameIndex, driverId);
    const controller = new AbortController();
    let cancelled = false;
    getReplayExplanation(
      raceId,
      frameIndex,
      driverId,
      fetch,
      undefined,
      controller.signal,
    )
      .then((explanation) => {
        if (!cancelled) setState({ key, view: { kind: "ready", explanation } });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        let view: LocalExplanationView;
        if (error instanceof V2ApiError && error.isUnavailable()) {
          view = { kind: "unavailable", reason: error.reason };
        } else if (error instanceof V2ApiError && error.status === 422) {
          view = { kind: "not_observable" };
        } else if (error instanceof V2ApiError && error.status === 404) {
          view = { kind: "not_observable" };
        } else if (error instanceof V2ApiError) {
          view = {
            kind: "error",
            message: `Local explanation unavailable (${error.status} ${error.code}).`,
          };
        } else {
          view = { kind: "error", message: "Local explanation request failed." };
        }
        setState({ key, view });
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [raceId, frameIndex, driverId]);

  return resolvedSelection(
    state,
    explanationSelectionKey(raceId, frameIndex, driverId),
    LOADING,
  );
}
