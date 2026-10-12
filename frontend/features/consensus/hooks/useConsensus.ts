// Consensus product state (V3.8G).
//
// Demo anchors only: the supported fixture, the simulation-ineligible
// state, and the product-excluded 2025 state. One availability request
// (cheap) followed by at most one compare request per anchor selection;
// session + abort guards reject stale responses. No polling, no loops,
// no science controls, no ground truth anywhere in this module.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConsensusAvailability,
  isConsensusUnsupported,
  postConsensusCompare,
  type ConsensusAnchor,
  type ConsensusAvailability,
  type ConsensusCompare,
} from "@/features/consensus/lib/consensusClient";
import { V2ApiError } from "@/lib/v2";

export type DemoAnchorId = "supported" | "sim-ineligible" | "excluded-2025";

export const DEMO_ANCHORS: Record<
  DemoAnchorId,
  { label: string; anchor: ConsensusAnchor; note: string }
> = {
  supported: {
    label: "2022-r03-R · Lap 2",
    anchor: {
      race_id: "2022-r03-R",
      anchor_lap_number: 2,
      anchor_state_time_s: null,
    },
    note: "Historical replay — illustrative supported state",
  },
  "sim-ineligible": {
    label: "2022-r19-R · Lap 1",
    anchor: {
      race_id: "2022-r19-R",
      anchor_lap_number: 1,
      anchor_state_time_s: null,
    },
    note: "Historical replay — simulation unavailable",
  },
  "excluded-2025": {
    label: "2025-r01-R · Lap 5",
    anchor: {
      race_id: "2025-r01-R",
      anchor_lap_number: 5,
      anchor_state_time_s: null,
    },
    note: "Product-excluded season",
  },
};

export type ConsensusView =
  | { kind: "loading" }
  | { kind: "result"; compare: ConsensusCompare }
  | {
      kind: "not-comparable";
      availability: ConsensusAvailability;
      reason: string | null;
      message: string;
    }
  | { kind: "unsupported"; reason: string | null; message: string }
  | { kind: "error"; message: string };

export function useConsensus() {
  const [anchorId, setAnchorId] = useState<DemoAnchorId>("supported");
  const [view, setView] = useState<ConsensusView>({ kind: "loading" });

  const sessionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const selectAnchor = useCallback((next: DemoAnchorId) => {
    sessionRef.current += 1;
    abortRef.current?.abort();
    setAnchorId(next);
    setView({ kind: "loading" });
  }, []);

  useEffect(() => {
    const anchor = DEMO_ANCHORS[anchorId].anchor;
    const session = ++sessionRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    // NOTE (V3.8H): no synchronous setView here; the initial state and
    // selectAnchor already establish { kind: "loading" } before this effect
    // runs (also satisfies react-hooks/set-state-in-effect).
    getConsensusAvailability(anchor, fetch, undefined, controller.signal)
      .then((availability) => {
        if (sessionRef.current !== session) return;
        if (availability.comparison !== "COMPARABLE") {
          setView({
            kind: "not-comparable",
            availability,
            reason:
              availability.simulation !== "AVAILABLE"
                ? availability.simulation_reason
                : availability.model_reason,
            message:
              availability.simulation !== "AVAILABLE"
                ? "Disagreement cannot be calculated because a source is unavailable at this factual state."
                : "Model unavailable at this state.",
          });
          return;
        }
        return postConsensusCompare(
          anchor,
          fetch,
          undefined,
          controller.signal,
        ).then((compare) => {
          if (sessionRef.current !== session) return;
          setView({ kind: "result", compare });
        });
      })
      .catch((error: unknown) => {
        if (sessionRef.current !== session) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (isConsensusUnsupported(error)) {
          const apiError = error as V2ApiError;
          setView({
            kind: "unsupported",
            reason: apiError.reason,
            message: apiError.message,
          });
          return;
        }
        setView({
          kind: "error",
          message: "Consensus request failed. Retry when the API is reachable.",
        });
      });
    return () => {
      controller.abort();
    };
  }, [anchorId]);

  const retry = useCallback(() => {
    selectAnchor(anchorId);
  }, [anchorId, selectAnchor]);

  return { anchorId, selectAnchor, view, retry };
}

export type ConsensusState = ReturnType<typeof useConsensus>;
