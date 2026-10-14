// Contextual decision-exploration state (V3.10G).
//
// Two narrow hooks over the frozen typed product clients — never the
// simulator, never result JSON, never a second cache:
//
//   useStrategyEntry        catalogue-backed availability + explicit cached compare
//   useCounterfactualEntry  per-anchor availability + explicit intervention compare
//
// Budget: at most one cheap catalogue load per race (shared module cache)
// plus one cheap availability GET per exact anchor. Changing race, frame,
// or driver re-derives entry state and ABANDONS any in-flight work —
// nothing auto-runs, nothing precomputes, and a stale response can never
// attach to a new workspace identity (session + request id + abort +
// response-identity check, mirroring the frozen expert hooks).
//
// Structure follows the lint-clean subscription pattern (repo precedent:
// useDriverTelemetry): module caches are read during render so warm states
// resolve with zero effects; effects only fetch cold entries and setState
// exclusively in async continuations or event handlers.
//
// Telemetry (F) and intelligence (E) toggles never touch these hooks, so
// they issue zero G requests by construction.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCounterfactualAvailability,
  getStrategyV3Availability,
  postCounterfactualCompare,
  postStrategyV3Compare,
  V2ApiError,
  type CounterfactualAvailability,
  type CounterfactualCompareResponse,
  type CounterfactualCompound,
  type Strategy2AvailabilityEntry,
  type Strategy2CompareResponse,
} from "@/lib/v2";
import {
  adaptDecisionTarget,
  eligibleNDomain,
  matchStrategyEntry,
  validateIntervention,
  type DecisionAnchor,
  type DecisionFrameMeta,
} from "@/features/pit-wall/lib/decisionAdapter";
import {
  classifyStrategy2Failure,
  strategy2ReasonCopy,
} from "@/features/strategy/lib/strategy2Machine";
import {
  buildCompareRequest,
  classifyCounterfactualFailure,
  counterfactualReasonCopy,
  type PlanDraft,
} from "@/features/counterfactuals/lib/counterfactualMachine";

export interface DecisionInput {
  raceId: string;
  frame: DecisionFrameMeta | null;
  selectedDriverId: string | null;
}

// Module caches: strategy catalogue per race, counterfactual availability
// per exact anchor. Shared across mounts; driver switches re-slice locally.

const strategyCatalogueCache = new Map<string, Strategy2AvailabilityEntry[]>();
const counterfactualAvailabilityCache = new Map<string, CounterfactualAvailability>();

// In-flight sharing: concurrent mounts, StrictMode re-runs, and fast
// scrubs share one identical GET instead of refiring it. Entries are
// removed on settle; sharees never abort each other.
const strategyCatalogueInflight = new Map<string, Promise<Strategy2AvailabilityEntry[]>>();
const counterfactualAvailabilityInflight = new Map<string, Promise<CounterfactualAvailability>>();

/** Test seam: clear module caches (tests only). */
export function clearDecisionCachesForTests(): void {
  strategyCatalogueCache.clear();
  counterfactualAvailabilityCache.clear();
  strategyCatalogueInflight.clear();
  counterfactualAvailabilityInflight.clear();
}

function anchorKey(anchor: DecisionAnchor): string {
  return `${anchor.race_id}|${anchor.anchor_driver_id}|${anchor.anchor_lap_number}|${anchor.anchor_state_time_s}`;
}

const STRATEGY_UNPRECOMPUTED =
  "Strategy analysis has not been precomputed for this exact state and driver. Nothing was simulated and no estimate is shown.";

// --- strategy -------------------------------------------------------------

export type StrategyEntryStatus =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "available"; entry: Strategy2AvailabilityEntry }
  | { kind: "unavailable"; message: string }
  | { kind: "unsupported"; message: string }
  | { kind: "running" }
  | { kind: "result"; response: Strategy2CompareResponse; requestKey: string }
  | { kind: "cache-miss"; requestKey: string }
  | { kind: "error"; message: string };

export function strategyEntryKey(parts: {
  anchor: DecisionAnchor;
  target: string;
}): string {
  return [
    parts.anchor.race_id,
    parts.anchor.anchor_driver_id,
    parts.anchor.anchor_lap_number,
    parts.anchor.anchor_state_time_s,
    parts.target,
    "cached",
  ].join("|");
}

type StrategyFetched =
  | { key: string; status: Extract<StrategyEntryStatus, { kind: "running" } | { kind: "result" } | { kind: "cache-miss" } | { kind: "error" } | { kind: "unsupported" } | { kind: "unavailable" }> };

export function useStrategyEntry(input: DecisionInput) {
  const [fetched, setFetched] = useState<StrategyFetched | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  // Cache-fill generation: the catalogue is read during render, so every
  // fill must schedule a render even when no fetched verdict exists yet —
  // otherwise a settled page would stick on "checking" forever.
  const [, setCacheVersion] = useState(0);
  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const adapted = adaptDecisionTarget(input.frame, input.selectedDriverId);
  const anchorJson = adapted.ok
    ? JSON.stringify({ anchor: adapted.anchor, target: adapted.targetDriverId })
    : null;

  // Render-phase resolution: refusal/idle and warm-catalogue states need no
  // effect. A fetched verdict (run result, fetch failure) applies only to
  // the identity it was issued for.
  const warm = adapted.ok ? strategyCatalogueCache.get(adapted.anchor.race_id) : undefined;
  let status: StrategyEntryStatus;
  if (!adapted.ok) {
    status =
      adapted.refusal.code === "NO_DRIVER" || adapted.refusal.code === "NO_FRAME"
        ? { kind: "idle" }
        : { kind: "unavailable", message: adapted.refusal.message };
  } else if (fetched && fetched.key === anchorJson) {
    status = fetched.status;
  } else if (warm) {
    const entry = matchStrategyEntry(warm, adapted.anchor, adapted.targetDriverId);
    status = entry
      ? { kind: "available", entry }
      : { kind: "unsupported", message: STRATEGY_UNPRECOMPUTED };
  } else {
    status = { kind: "checking" };
  }

  useEffect(() => {
    if (!adapted.ok || !anchorJson) return;
    const raceId = adapted.anchor.race_id;
    if (strategyCatalogueCache.has(raceId)) return;
    const session = sessionRef.current;
    const key = anchorJson;
    let cancelled = false;
    let inflight = strategyCatalogueInflight.get(raceId);
    if (!inflight) {
      inflight = getStrategyV3Availability(fetch, undefined, raceId).then(
        (catalogue) => catalogue.entries,
      );
      strategyCatalogueInflight.set(raceId, inflight);
    }
    inflight.then(
      (entries) => {
        if (strategyCatalogueInflight.get(raceId) === inflight) {
          strategyCatalogueInflight.delete(raceId);
        }
        // Always fill: the key is exact, so even a superseded resolution
        // warms the right entry. Stale guards below gate STATE only.
        strategyCatalogueCache.set(raceId, entries);
        if (cancelled || !mountedRef.current || sessionRef.current !== session) return;
        // Warm render path takes over; clear any stale fetch failure and
        // schedule the render that reads the warm cache.
        setFetched((current) => (current && current.key === key ? null : current));
        setCacheVersion((v) => v + 1);
      },
      (error: unknown) => {
        if (strategyCatalogueInflight.get(raceId) === inflight) {
          strategyCatalogueInflight.delete(raceId);
        }
        if (cancelled || !mountedRef.current || sessionRef.current !== session) return;
        const message =
          error instanceof V2ApiError && error.code === "unknown_race"
            ? "Strategy supports 2018–2024 only. This race has no analysis."
            : "Strategy catalogue failed to load. Check the API server.";
        setFetched({ key, status: { kind: "unavailable", message } });
      },
    );
    return () => {
      cancelled = true;
    };
    // anchorJson is the stable identity of (anchor, target).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input.raceId, anchorJson, retryNonce]);

  // A workspace move abandons in-flight compare work. The keyed render
  // path already ignores it; aborting also frees the connection. No state
  // is written here.
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, [anchorJson]);

  const retry = useCallback(() => {
    const current = adaptDecisionTarget(input.frame, input.selectedDriverId);
    sessionRef.current += 1;
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    if (current.ok) strategyCatalogueCache.delete(current.anchor.race_id);
    setFetched(null);
    setRetryNonce((n) => n + 1);
  }, [input.frame, input.selectedDriverId]);

  const run = useCallback(() => {
    const current = adaptDecisionTarget(input.frame, input.selectedDriverId);
    if (!current.ok) return;
    const { anchor, targetDriverId } = current;
    const key = strategyEntryKey({ anchor, target: targetDriverId });
    const identity = JSON.stringify({ anchor, target: targetDriverId });
    const session = sessionRef.current;
    const requestId = ++requestIdRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setFetched({ key: identity, status: { kind: "running" } });
    // Cache-first, full frozen 9-action set (alternatives omitted), explicit
    // user intent only. Live execution is never reachable from this surface.
    postStrategyV3Compare(
      {
        race_id: anchor.race_id,
        anchor_driver_id: anchor.anchor_driver_id,
        anchor_lap_number: anchor.anchor_lap_number,
        anchor_state_time_s: anchor.anchor_state_time_s,
        target_driver_id: targetDriverId,
        mode: "cached",
      },
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
          response.anchor_state_time_s !== anchor.anchor_state_time_s ||
          response.target_driver_id !== targetDriverId
        ) {
          return;
        }
        if (!response.supported) {
          setFetched({
            key: identity,
            status: {
              kind: "unsupported",
              message: strategy2ReasonCopy(response.unsupported_reason),
            },
          });
          return;
        }
        setFetched({ key: identity, status: { kind: "result", response, requestKey: key } });
      })
      .catch((error: unknown) => {
        if (requestId !== requestIdRef.current || session !== sessionRef.current) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        const failure =
          error instanceof V2ApiError
            ? classifyStrategy2Failure({
                status: error.status,
                code: error.code,
                reason: error.reason,
                detail: error.message,
              })
            : { kind: "server" as const, message: "Strategy comparison request failed. Retry when the API is reachable." };
        if (failure.kind === "cache-miss") {
          setFetched({ key: identity, status: { kind: "cache-miss", requestKey: key } });
        } else {
          setFetched({ key: identity, status: { kind: "error", message: failure.message } });
        }
      });
  }, [input.frame, input.selectedDriverId]);

  return { status, run, retry };
}

export type StrategyEntry = ReturnType<typeof useStrategyEntry>;

// --- counterfactual --------------------------------------------------------

export type CounterfactualEntryStatus =
  | { kind: "idle" }
  | { kind: "checking" }
  | {
      kind: "available";
      availability: CounterfactualAvailability;
      nMin: number;
      nMax: number;
      decisionLap: number;
      compounds: string[];
    }
  | { kind: "unavailable"; message: string }
  | { kind: "unsupported"; reason: string | null; message: string }
  | { kind: "invalid"; message: string }
  | {
      kind: "running";
      nMin: number;
      nMax: number;
      decisionLap: number;
      compounds: string[];
    }
  | {
      kind: "result";
      response: CounterfactualCompareResponse;
      requestKey: string;
      nMin: number;
      nMax: number;
      decisionLap: number;
      compounds: string[];
    }
  | { kind: "cache-miss"; requestKey: string }
  | { kind: "error"; message: string };

type CounterfactualFetched =
  | { key: string; status: Extract<CounterfactualEntryStatus, { kind: "running" } | { kind: "result" } | { kind: "cache-miss" } | { kind: "error" } | { kind: "invalid" } | { kind: "unsupported" } | { kind: "unavailable" }> };

function resolveCounterfactualAvailability(
  availability: CounterfactualAvailability,
  targetDriverId: string,
): CounterfactualEntryStatus {
  if (!availability.supported) {
    return {
      kind: "unsupported",
      reason: availability.reason_code,
      message: counterfactualReasonCopy(availability.reason_code),
    };
  }
  const domain = eligibleNDomain(availability.drivers, targetDriverId);
  if (domain === null || !availability.eligible_targets.includes(targetDriverId)) {
    return {
      kind: "unsupported",
      reason: "TARGET_NOT_PRESENT",
      message:
        "The selected driver admits no scheduled intervention at this exact state. The selection is kept — nothing is substituted.",
    };
  }
  return {
    kind: "available",
    availability,
    nMin: domain.min,
    nMax: domain.max,
    decisionLap: domain.decisionLap,
    compounds: availability.supported_compounds,
  };
}

export function useCounterfactualEntry(input: DecisionInput) {
  const [fetched, setFetched] = useState<CounterfactualFetched | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  // Cache-fill generation: availability is read during render, so every
  // fill must schedule a render even when no fetched verdict exists yet.
  const [, setCacheVersion] = useState(0);
  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const adapted = adaptDecisionTarget(input.frame, input.selectedDriverId);
  const anchorJson = adapted.ok
    ? JSON.stringify({ anchor: adapted.anchor, target: adapted.targetDriverId })
    : null;

  const warm = adapted.ok
    ? counterfactualAvailabilityCache.get(anchorKey(adapted.anchor))
    : undefined;
  let status: CounterfactualEntryStatus;
  if (!adapted.ok) {
    status =
      adapted.refusal.code === "NO_DRIVER" || adapted.refusal.code === "NO_FRAME"
        ? { kind: "idle" }
        : { kind: "unavailable", message: adapted.refusal.message };
  } else if (fetched && fetched.key === anchorJson) {
    status = fetched.status;
  } else if (warm) {
    status = resolveCounterfactualAvailability(warm, adapted.targetDriverId);
  } else {
    status = { kind: "checking" };
  }

  useEffect(() => {
    if (!adapted.ok || !anchorJson) return;
    const anchor = adapted.anchor;
    const cacheId = anchorKey(anchor);
    if (counterfactualAvailabilityCache.has(cacheId)) return;
    const session = sessionRef.current;
    const key = anchorJson;
    let cancelled = false;
    let inflight = counterfactualAvailabilityInflight.get(cacheId);
    if (!inflight) {
      inflight = getCounterfactualAvailability(
        {
          race_id: anchor.race_id,
          anchor_driver_id: anchor.anchor_driver_id,
          anchor_lap_number: anchor.anchor_lap_number,
          anchor_state_time_s: anchor.anchor_state_time_s,
        },
        fetch,
        undefined,
      );
      counterfactualAvailabilityInflight.set(cacheId, inflight);
    }
    inflight.then(
      (availability) => {
        if (counterfactualAvailabilityInflight.get(cacheId) === inflight) {
          counterfactualAvailabilityInflight.delete(cacheId);
        }
        // Always fill: the key is exact, so even a superseded resolution
        // warms the right entry. Stale guards below gate STATE only.
        counterfactualAvailabilityCache.set(cacheId, availability);
        if (cancelled || !mountedRef.current || sessionRef.current !== session) return;
        setFetched((current) => (current && current.key === key ? null : current));
        setCacheVersion((v) => v + 1);
      },
      (error: unknown) => {
        if (counterfactualAvailabilityInflight.get(cacheId) === inflight) {
          counterfactualAvailabilityInflight.delete(cacheId);
        }
        if (cancelled || !mountedRef.current || sessionRef.current !== session) return;
        const message =
          error instanceof V2ApiError && error.code === "unknown_race"
            ? "Alternative exploration supports 2018–2024 only. This race has no analysis."
            : "Alternative availability failed to load. Check the API server.";
        setFetched({ key, status: { kind: "unavailable", message } });
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input.raceId, anchorJson, retryNonce]);

  // A workspace move abandons in-flight compare work. The keyed render
  // path already ignores it; aborting also frees the connection. No state
  // is written here.
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, [anchorJson]);

  const retry = useCallback(() => {
    const current = adaptDecisionTarget(input.frame, input.selectedDriverId);
    sessionRef.current += 1;
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    if (current.ok) counterfactualAvailabilityCache.delete(anchorKey(current.anchor));
    setFetched(null);
    setRetryNonce((n) => n + 1);
  }, [input.frame, input.selectedDriverId]);

  const run = useCallback(
    (n: number, compound: CounterfactualCompound) => {
      const current = adaptDecisionTarget(input.frame, input.selectedDriverId);
      if (!current.ok) return;
      const { anchor, targetDriverId } = current;
      const identity = JSON.stringify({ anchor, target: targetDriverId });
      const availability = counterfactualAvailabilityCache.get(anchorKey(anchor)) ?? null;
      const domain = availability
        ? eligibleNDomain(availability.drivers, targetDriverId)
        : null;
      const validity = validateIntervention(
        n,
        domain,
        compound,
        availability?.supported_compounds ?? [],
      );
      if (!validity.ok) {
        sessionRef.current += 1;
        requestIdRef.current += 1;
        abortRef.current?.abort();
        abortRef.current = null;
        setFetched({ key: identity, status: { kind: "invalid", message: validity.reason } });
        return;
      }
      // validateIntervention rejects null domains, so a valid verdict proves
      // the domain exists; the explicit guard below is for the type checker.
      if (domain === null || availability === null) return;
      const alt: PlanDraft = {
        target_driver_ids: [targetDriverId],
        interventions: [
          { target_driver_id: targetDriverId, lap_offset_n: n, requested_compound: compound },
        ],
      };
      const requestKey = [
        anchor.race_id,
        anchor.anchor_driver_id,
        anchor.anchor_lap_number,
        anchor.anchor_state_time_s,
        targetDriverId,
        n,
        compound,
      ].join("|");
      const session = sessionRef.current;
      const requestId = ++requestIdRef.current;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      // The intervention domain rides along so the form persists across
      // running → result without re-derivation (V3.10H §33).
      const formDomain = {
        nMin: domain.min,
        nMax: domain.max,
        decisionLap: domain.decisionLap,
        compounds: [...availability.supported_compounds],
      };
      setFetched({ key: identity, status: { kind: "running", ...formDomain } });
      // REFERENCE_VS_PLAN only: one supported PIT_IN_N_LAPS intervention
      // against the simulated no-intervention reference. Explicit intent only.
      postCounterfactualCompare(
        buildCompareRequest(anchor, "REFERENCE_VS_PLAN", null, alt, null),
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
            setFetched({
              key: identity,
              status: {
                kind: "unsupported",
                reason: response.reason_code,
                message: counterfactualReasonCopy(response.reason_code),
              },
            });
            return;
          }
          setFetched({ key: identity, status: { kind: "result", response, requestKey, ...formDomain } });
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
              : { kind: "server" as const, message: "Alternative comparison request failed. Retry when the API is reachable." };
          if (failure.kind === "cache-miss") {
            setFetched({ key: identity, status: { kind: "cache-miss", requestKey } });
          } else if (failure.kind === "unknown-race" || failure.kind === "unavailable") {
            setFetched({ key: identity, status: { kind: "unavailable", message: failure.message } });
          } else if (failure.kind === "invalid") {
            setFetched({ key: identity, status: { kind: "invalid", message: failure.message } });
          } else {
            setFetched({ key: identity, status: { kind: "error", message: failure.message } });
          }
        });
    },
    [input.frame, input.selectedDriverId],
  );

  return { status, run, retry };
}

export type CounterfactualEntry = ReturnType<typeof useCounterfactualEntry>;
