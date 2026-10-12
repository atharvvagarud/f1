// Counterfactual Explorer product state (V3.7G).
//
// API-only: availability + compare over the frozen F contract. Ordinary
// interaction sends no count, no seed, and no live/compute-mode flag —
// such fields do not exist in the request type. Explicit Run only:
// changing any control clears the result; stale responses are rejected
// by session + request key and aborted in flight. Cache misses and
// unsupported states render factual product states — the hook never
// falls back to another engine, zeros, or placeholders. Demo-first:
// the deterministic F demo anchor auto-runs once from cache on load.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  V2ApiError,
  fetchFullTimeline,
  getCounterfactualAvailability,
  getV2Races,
  postCounterfactualCompare,
  type CounterfactualAvailability,
  type CounterfactualCompareResponse,
  type CounterfactualCompound,
  type CounterfactualForm,
  type ReplayFrameMeta,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  DEMO_ANCHOR,
  DEMO_DEFAULT_PLAN,
  DEMO_TARGET,
  MAX_INTERVENTIONS,
  buildCompareRequest,
  counterfactualReasonCopy,
  classifyCounterfactualFailure,
  draftRequestKey,
  type PlanDraft,
} from "@/features/counterfactuals/lib/counterfactualMachine";

export type InterventionDraft = {
  id: string;
  target_driver_id: string;
  lap_offset_n: number;
  requested_compound: CounterfactualCompound;
};

export type CounterfactualView =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "result"; response: CounterfactualCompareResponse; requestKey: string }
  | { kind: "cache-miss"; requestKey: string }
  | { kind: "unsupported"; reason: string | null; message: string; requestKey: string }
  | { kind: "unavailable"; message: string }
  | { kind: "invalid"; message: string }
  | { kind: "error"; message: string };

let interventionSeq = 0;
function newIntervention(
  target: string,
  n = 2,
  compound: CounterfactualCompound = "MEDIUM",
): InterventionDraft {
  interventionSeq += 1;
  return { id: `iv-${interventionSeq}`, target_driver_id: target, lap_offset_n: n, requested_compound: compound };
}

function draftOf(targets: string[], items: InterventionDraft[]): PlanDraft {
  return {
    target_driver_ids: [...targets],
    interventions: items.map((i) => ({
      target_driver_id: i.target_driver_id,
      lap_offset_n: i.lap_offset_n,
      requested_compound: i.requested_compound,
    })),
  };
}

export function useCounterfactuals() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [raceId, setRaceId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);

  const [availability, setAvailability] = useState<CounterfactualAvailability | null>(null);
  const [availabilityLoading, setAvailabilityLoading] = useState(true);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);

  const [form, setForm] = useState<CounterfactualForm>("REFERENCE_VS_PLAN");
  const [altTargets, setAltTargets] = useState<string[]>([DEMO_TARGET]);
  const [altItems, setAltItems] = useState<InterventionDraft[]>([
    { id: "iv-demo", target_driver_id: "perez", lap_offset_n: 1, requested_compound: "MEDIUM" },
  ]);
  const [baseTargets, setBaseTargets] = useState<string[]>([DEMO_TARGET]);
  const [baseItems, setBaseItems] = useState<InterventionDraft[]>([
    { id: "iv-base", target_driver_id: "perez", lap_offset_n: 2, requested_compound: "MEDIUM" },
  ]);
  const [rival, setRival] = useState<string | null>(null);
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [provenanceOpen, setProvenanceOpen] = useState(false);

  const [view, setView] = useState<CounterfactualView>({ kind: "idle" });

  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const autoRanRef = useRef(false);

  const selectedFrame = frames[frameIndex] ?? null;
  const anchor = useMemo(
    () =>
      selectedFrame && raceId
        ? {
            race_id: raceId,
            anchor_driver_id: selectedFrame.anchor_driver_id,
            anchor_lap_number: selectedFrame.anchor_lap_number,
            anchor_state_time_s: selectedFrame.anchor_state_time_s,
          }
        : null,
    [selectedFrame, raceId],
  );

  const altDraft = useMemo(() => draftOf(altTargets, altItems), [altTargets, altItems]);
  const baseDraft = useMemo(() => draftOf(baseTargets, baseItems), [baseTargets, baseItems]);

  const canRun =
    anchor !== null &&
    availability !== null &&
    availability.supported &&
    altTargets.length > 0 &&
    altItems.length > 0 &&
    altItems.length <= MAX_INTERVENTIONS &&
    (form === "REFERENCE_VS_PLAN" || (baseTargets.length > 0 && baseItems.length > 0)) &&
    view.kind !== "running" &&
    !availabilityLoading;

  const clearResult = useCallback(() => {
    setView({ kind: "idle" });
  }, []);

  const bumpSession = useCallback(() => {
    sessionRef.current += 1;
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const loadTimeline = useCallback(
    (nextRaceId: string, session: number) => {
      setTimelineLoading(true);
      setTimelineError(null);
      fetchFullTimeline(nextRaceId)
        .then((loaded) => {
          if (sessionRef.current !== session) return;
          setFrames(loaded);
          if (loaded.length === 0) setAvailabilityLoading(false);
          const demoIndex = loaded.findIndex(
            (frame) =>
              nextRaceId === DEMO_ANCHOR.race_id &&
              frame.anchor_driver_id === DEMO_ANCHOR.anchor_driver_id &&
              frame.anchor_lap_number === DEMO_ANCHOR.anchor_lap_number &&
              frame.anchor_state_time_s === DEMO_ANCHOR.anchor_state_time_s,
          );
          setFrameIndex(demoIndex >= 0 ? demoIndex : 0);
          setTimelineLoading(false);
        })
        .catch((error: unknown) => {
          if (sessionRef.current !== session) return;
          setTimelineLoading(false);
          setTimelineError(
            error instanceof V2ApiError && error.code === "unknown_race"
              ? `Unknown race ${nextRaceId}. Counterfactuals support 2018–2024 only.`
              : `Timeline failed to load for ${nextRaceId}.`,
          );
        });
    },
    [],
  );

  const selectRace = useCallback(
    (nextRaceId: string | null) => {
      if (!nextRaceId) return;
      bumpSession();
      clearResult();
      setRaceId(nextRaceId);
      setFrames([]);
      setFrameIndex(0);
      setAvailability(null);
      setAvailabilityError(null);
      setAvailabilityLoading(true);
      setRival(null);
      loadTimeline(nextRaceId, sessionRef.current);
    },
    [bumpSession, clearResult, loadTimeline],
  );

  // --- initial load: races, then the deterministic demo race timeline ---
  useEffect(() => {
    let cancelled = false;
    getV2Races()
      .then((list) => {
        if (cancelled) return;
        const ordered = [...list.races].sort(
          (a, b) =>
            a.season - b.season ||
            a.round_no - b.round_no ||
            (a.race_id < b.race_id ? -1 : a.race_id > b.race_id ? 1 : 0),
        );
        setRaces(ordered);
        const demoRace = ordered.some((r) => r.race_id === DEMO_ANCHOR.race_id)
          ? DEMO_ANCHOR.race_id
          : (ordered[0]?.race_id ?? null);
        if (demoRace) {
          setRaceId(demoRace);
          setFrames([]);
          setAvailability(null);
          loadTimeline(demoRace, sessionRef.current);
        }
      })
      .catch(() => {
        if (!cancelled) setRacesError("Race list failed to load. Check the API server.");
      })
      .finally(() => {
        if (!cancelled) setRacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadTimeline]);

  // --- availability for the selected anchor (cheap, never simulates) ---
  // Loading flags are set at trigger sites (selection callbacks and
  // timeline resolution), never synchronously in this effect body.
  useEffect(() => {
    if (!raceId || !selectedFrame) return;
    const session = sessionRef.current;
    const controller = new AbortController();
    getCounterfactualAvailability(
      {
        race_id: raceId,
        anchor_driver_id: selectedFrame.anchor_driver_id,
        anchor_lap_number: selectedFrame.anchor_lap_number,
        anchor_state_time_s: selectedFrame.anchor_state_time_s,
      },
      fetch,
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (sessionRef.current !== session) return;
        setAvailability(result);
        setAvailabilityLoading(false);
        if (result.supported && result.eligible_targets.length > 0) {
          const first = result.eligible_targets[0];
          setAltTargets((current) =>
            current.length > 0 && current.every((t) => result.eligible_targets.includes(t))
              ? current
              : [first],
          );
          setAltItems((current) =>
            current.map((item) =>
              result.eligible_targets.includes(item.target_driver_id)
                ? item
                : { ...item, target_driver_id: first },
            ),
          );
        }
        setRival((current) =>
          current !== null && !result.rival_candidates.includes(current) ? null : current,
        );
      })
      .catch((error: unknown) => {
        if (sessionRef.current !== session) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAvailability(null);
        setAvailabilityLoading(false);
        setAvailabilityError(
          error instanceof V2ApiError
            ? `Availability failed (${error.code}).`
            : "Availability failed to load.",
        );
      });
    return () => {
      controller.abort();
    };
  }, [raceId, selectedFrame]);

  const selectFrame = useCallback(
    (index: number) => {
      bumpSession();
      clearResult();
      setFrameIndex(Math.max(0, Math.min(index, frames.length - 1)));
      setAvailability(null);
      setAvailabilityError(null);
      setAvailabilityLoading(true);
    },
    [bumpSession, clearResult, frames.length],
  );

  const run = useCallback(() => {
    if (!anchor || !availability?.supported) return;
    if (altTargets.length === 0 || altItems.length === 0) return;
    if (form === "PLAN_VS_PLAN" && (baseTargets.length === 0 || baseItems.length === 0)) return;
    const key = draftRequestKey({
      raceId: anchor.race_id,
      anchorDriverId: anchor.anchor_driver_id,
      anchorLapNumber: anchor.anchor_lap_number,
      anchorStateTime: anchor.anchor_state_time_s,
      form,
      base: form === "PLAN_VS_PLAN" ? baseDraft : null,
      alt: altDraft,
      rival,
    });
    const session = sessionRef.current;
    const requestId = ++requestIdRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setView({ kind: "running" });
    postCounterfactualCompare(
      buildCompareRequest(anchor, form, form === "PLAN_VS_PLAN" ? baseDraft : null, altDraft, rival),
      fetch,
      undefined,
      controller.signal,
    )
      .then((response) => {
        if (requestId !== requestIdRef.current || session !== sessionRef.current) return;
        if (
          response.race_id !== anchor.race_id ||
          response.anchor_driver_id !== anchor.anchor_driver_id ||
          response.anchor_lap_number !== anchor.anchor_lap_number ||
          response.anchor_state_time_s !== anchor.anchor_state_time_s
        ) {
          return;
        }
        if (!response.supported) {
          setView({
            kind: "unsupported",
            reason: response.reason_code,
            message: counterfactualReasonCopy(response.reason_code),
            requestKey: key,
          });
          return;
        }
        setView({ kind: "result", response, requestKey: key });
      })
      .catch((error: unknown) => {
        if (requestId !== requestIdRef.current || session !== sessionRef.current) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        const failure =
          error instanceof V2ApiError
            ? classifyCounterfactualFailure({
                status: error.status,
                code: error.code,
                reason: error.reason,
                detail: error.message,
              })
            : { kind: "server" as const, message: "Counterfactual comparison request failed. Retry when the API is reachable." };
        if (failure.kind === "cache-miss") {
          setView({ kind: "cache-miss", requestKey: key });
        } else if (failure.kind === "unknown-race" || failure.kind === "unavailable") {
          setView({ kind: "unavailable", message: failure.message });
        } else if (failure.kind === "invalid") {
          setView({ kind: "invalid", message: failure.message });
        } else {
          setView({ kind: "error", message: failure.message });
        }
      });
  }, [anchor, availability, altTargets, altItems, baseTargets, baseItems, form, altDraft, baseDraft, rival]);

  // Demo-first: auto-run the deterministic default once it is runnable.
  // Deferred past render (timeout callback, not the effect body).
  useEffect(() => {
    if (!autoRanRef.current && canRun && view.kind === "idle") {
      autoRanRef.current = true;
      const timer = setTimeout(run, 0);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [canRun, view.kind, run]);

  const retry = useCallback(() => {
    if (view.kind === "error" || view.kind === "invalid" || view.kind === "unsupported" || view.kind === "cache-miss") {
      run();
    }
  }, [view.kind, run]);

  const touch = useCallback(() => {
    bumpSession();
    clearResult();
  }, [bumpSession, clearResult]);

  const setFormMode = useCallback(
    (next: CounterfactualForm) => {
      touch();
      setForm(next);
    },
    [touch],
  );

  const applyPreset = useCallback(
    (preset: { form: CounterfactualForm; base: PlanDraft | null; alt: PlanDraft; rival: string | null }) => {
      touch();
      setForm(preset.form);
      const toItems = (draft: PlanDraft): InterventionDraft[] =>
        draft.interventions.map((i) => ({
          ...newIntervention(i.target_driver_id, i.lap_offset_n, i.requested_compound),
        }));
      setAltTargets([...preset.alt.target_driver_ids]);
      setAltItems(toItems(preset.alt));
      if (preset.base) {
        setBaseTargets([...preset.base.target_driver_ids]);
        setBaseItems(toItems(preset.base));
      }
      setRival(preset.rival);
    },
    [touch],
  );

  return {
    races,
    racesLoading,
    racesError,
    raceId,
    selectRace,
    frames,
    totalFrames: frames.length,
    timelineLoading,
    timelineError,
    frameIndex,
    selectedFrame,
    selectFrame,
    anchor,
    availability,
    availabilityLoading,
    availabilityError,
    form,
    setForm: setFormMode,
    altTargets,
    setAltTargets: (next: string[]) => {
      touch();
      setAltTargets(next);
    },
    altItems,
    setAltItems: (next: InterventionDraft[]) => {
      touch();
      setAltItems(next.slice(0, MAX_INTERVENTIONS));
    },
    baseTargets,
    setBaseTargets: (next: string[]) => {
      touch();
      setBaseTargets(next);
    },
    baseItems,
    setBaseItems: (next: InterventionDraft[]) => {
      touch();
      setBaseItems(next.slice(0, MAX_INTERVENTIONS));
    },
    rival,
    setRival: (next: string | null) => {
      touch();
      setRival(next);
    },
    methodologyOpen,
    setMethodologyOpen,
    provenanceOpen,
    setProvenanceOpen,
    view,
    canRun,
    run,
    retry,
    applyPreset,
    demoDefaults: { anchor: DEMO_ANCHOR, plan: DEMO_DEFAULT_PLAN },
  };
}

export type CounterfactualsState = ReturnType<typeof useCounterfactuals>;
