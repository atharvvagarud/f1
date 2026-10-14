// WorkspaceProvider — React binding over the pure workspace core (V3.10B §9).
//
// Narrowly typed operations only: setRace / seekFrame / selectDriver /
// clearDriver (+ goToNextFrame/goToPreviousFrame equivalents deferred to the
// replay migration in V3.10C/D; replay owns stepping until then).
//
// URL ownership (§11): URL initializes workspace state exactly once on mount
// (client-only effect; SSR renders idle null so hydration always matches).
// Thereafter workspace transitions update the URL through one path with an
// explicit push/replace classification (§13). The URL is never re-read after
// init, so no bidirectional loop is possible.
//
// No science fetching here (§27): this provider owns identity only.
// Presentation state (tabs, drawers, hover, sort) stays local (§24).

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { clearDriver as coreClearDriver, historyActionFor, seekFrame as coreSeekFrame, selectDriver as coreSelectDriver, setRace as coreSetRace, type WorkspaceState, type WorkspaceTransitionKind } from "../lib/workspaceState.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { hydrateFromUrl, serializeWorkspace } from "../lib/workspaceUrl.ts";

export interface WorkspaceContextValue {
  /** Canonical identity; null until a race is selected or a deep link hydrates. */
  state: WorkspaceState | null;
  /** True once the mount-time URL hydration attempt has run. */
  hydrated: boolean;
  /** Non-fatal init failure (malformed deep link); app must not crash. */
  initError: string | null;
  /** Last transition failure message, if any; null after a success. */
  lastError: string | null;
  setRace: (
    raceId: string,
    roster?: readonly string[] | null,
  ) => boolean;
  seekFrame: (frameIndex: number, totalFrames?: number | null) => boolean;
  selectDriver: (
    driverId: string,
    roster?: readonly string[] | null,
  ) => boolean;
  clearDriver: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function hasWorkspaceParams(search: string): boolean {
  try {
    const params = new URLSearchParams(
      search.startsWith("?") ? search.slice(1) : search,
    );
    return params.has("race") || params.has("frame");
  } catch {
    return false;
  }
}

function currentSearch(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.location.search;
  } catch {
    return null;
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  // Transition that produced the current state; drives push-vs-replace.
  const lastTransitionRef = useRef<WorkspaceTransitionKind | null>(null);
  // Synchronous mirror of state so operations can validate against the
  // current identity and report success/failure in the same tick (React
  // state updaters run later and cannot carry a return value).
  const stateRef = useRef<WorkspaceState | null>(null);

  // Mount-only hydration: URL -> state, once. Never re-read afterwards.
  // The URL is the external system here; syncing it into state on mount is
  // exactly what this effect is for (and keeps SSR/client HTML identical).
  /* eslint-disable react-hooks/set-state-in-effect -- mount-only external-system hydration */
  useEffect(() => {
    const search = currentSearch();
    if (search === null) {
      setHydrated(true);
      return;
    }
    if (!hasWorkspaceParams(search)) {
      // No deep link: idle until race selection. Not an error.
      setHydrated(true);
      return;
    }
    const result = hydrateFromUrl(search);
    if (result.ok) {
      lastTransitionRef.current = "HYDRATE";
      stateRef.current = result.state;
      setState(result.state);
    } else {
      // Malformed deep link: stay idle, record explicitly, never crash.
      setInitError(result.error.message);
    }
    setHydrated(true);
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  // One-directional sync: state -> URL. Guarded against loops by comparing
  // against the live URL before writing; HYDRATE never writes.
  useEffect(() => {
    if (!hydrated || state === null) return;
    const transition = lastTransitionRef.current;
    if (transition === null || transition === "HYDRATE") return;
    const action = historyActionFor(transition);
    if (action === "none") return;
    const next = `?${serializeWorkspace(state)}`;
    const search = currentSearch();
    if (search === null || search === next) return;
    try {
      if (action === "push") {
        window.history.pushState(null, "", next);
      } else {
        window.history.replaceState(null, "", next);
      }
    } catch {
      // URL sync is a convenience; never break workspace state.
    }
  }, [hydrated, state]);

  const setRace = useCallback(
    (raceId: string, roster: readonly string[] | null = null): boolean => {
      const result = coreSetRace(stateRef.current, raceId, roster);
      if (!result.ok) {
        setLastError(result.error.message);
        return false;
      }
      lastTransitionRef.current = "SET_RACE";
      stateRef.current = result.state;
      setLastError(null);
      setState(result.state);
      return true;
    },
    [],
  );

  const seekFrame = useCallback(
    (frameIndex: number, totalFrames: number | null = null): boolean => {
      const prev = stateRef.current;
      if (prev === null) {
        setLastError("No race selected; cannot seek.");
        return false;
      }
      const result = coreSeekFrame(prev, frameIndex, totalFrames);
      if (!result.ok) {
        setLastError(result.error.message);
        return false;
      }
      lastTransitionRef.current = "SEEK_FRAME";
      stateRef.current = result.state;
      setLastError(null);
      setState(result.state);
      return true;
    },
    [],
  );

  const selectDriver = useCallback(
    (driverId: string, roster: readonly string[] | null = null): boolean => {
      const prev = stateRef.current;
      if (prev === null) {
        setLastError("No race selected; cannot select driver.");
        return false;
      }
      const result = coreSelectDriver(prev, driverId, roster);
      if (!result.ok) {
        setLastError(result.error.message);
        return false;
      }
      lastTransitionRef.current = "SELECT_DRIVER";
      stateRef.current = result.state;
      setLastError(null);
      setState(result.state);
      return true;
    },
    [],
  );

  const clearDriver = useCallback((): void => {
    const prev = stateRef.current;
    if (prev === null) return;
    lastTransitionRef.current = "CLEAR_DRIVER";
    const next = coreClearDriver(prev);
    stateRef.current = next;
    setLastError(null);
    setState(next);
  }, []);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      state,
      hydrated,
      initError,
      lastError,
      setRace,
      seekFrame,
      selectDriver,
      clearDriver,
    }),
    [
      state,
      hydrated,
      initError,
      lastError,
      setRace,
      seekFrame,
      selectDriver,
      clearDriver,
    ],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

/** Access the workspace. Throws when used outside the provider (fail loudly in dev, never silently fork state). */
export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (ctx === null) {
    throw new Error("useWorkspace must be used within WorkspaceProvider.");
  }
  return ctx;
}
