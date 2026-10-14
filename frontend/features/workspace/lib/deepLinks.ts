// Typed deep-link helpers: pit-wall -> expert routes (V3.10B §19).
//
// Each helper carries the canonical identity (race, frame/T, driver) where
// the target route supports it. Targets adopt the contract incrementally;
// nothing here redesigns or forces changes on those pages. Adoption status
// is recorded honestly per route in ROUTE_WORKSPACE_ADOPTION.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { serializeWorkspace } from "./workspaceUrl.ts";
import type { WorkspaceState } from "./workspaceState.ts";

export type WorkspaceLinkedRoute =
  | "/replay"
  | "/simulator"
  | "/strategy"
  | "/counterfactuals"
  | "/consensus"
  | "/uncertainty";

export interface RouteAdoption {
  route: WorkspaceLinkedRoute;
  /** Canonical params the target route consumes today. */
  consumes: readonly ("race" | "frame" | "driver")[];
  /** Remaining adoption work (owned by later V3.10 stages, not B). */
  deferred: string;
}

export const ROUTE_WORKSPACE_ADOPTION: readonly RouteAdoption[] = [
  {
    route: "/replay",
    consumes: ["race", "frame"],
    deferred:
      "driver: ReplayView owns local race-tagged selection; workspace-provided driver adoption is V3.10C/D work.",
  },
  {
    route: "/simulator",
    consumes: [],
    deferred:
      "race+frame: useSimulator owns independent identity; adapter adoption is later-stage work.",
  },
  {
    route: "/strategy",
    consumes: ["race", "frame", "driver"],
    deferred:
      "none: V3.10G hydrates race + exact frame + target from the canonical deep link via useExpertWorkspaceHydration; comparison itself stays explicit and cache-first.",
  },
  {
    route: "/counterfactuals",
    consumes: ["race", "frame", "driver"],
    deferred:
      "none: V3.10G hydrates race + exact frame + intervention targets from the canonical deep link via useExpertWorkspaceHydration; the intervention itself stays user-controlled.",
  },
  {
    route: "/consensus",
    consumes: [],
    deferred:
      "race+frame+driver: fixed DEMO_ANCHORS today; canonical-T comparison is later-stage work.",
  },
  {
    route: "/uncertainty",
    consumes: [],
    deferred:
      "race+frame+driver: fixed DEMO_ANCHORS today; canonical-T comparison is later-stage work.",
  },
];

/**
 * Builds "<route>?race=X&frame=N[&driver=D]". Emits the full canonical
 * identity unconditionally — forward-compatible: routes ignore params they
 * do not consume yet, and adopt them per ROUTE_WORKSPACE_ADOPTION.
 */
export function workspaceDeepLink(
  route: WorkspaceLinkedRoute,
  state: WorkspaceState,
): string {
  return `${route}?${serializeWorkspace(state)}`;
}
