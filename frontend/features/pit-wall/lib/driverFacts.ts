// Pure selected-driver facts for the Pit Wall driver region (V3.10C).
//
// Everything here renders backend facts already present at the canonical
// replay frame: position, gap, tyre/stint, pit stops. No probabilities, no
// simulated values, no intelligence — V3.10E owns that. Nulls render as
// em-dash, never zero; a selected driver absent from the roster is reported
// as no-evidence (identity stays intact per V3.10B §16).

import type { DriverRaceState } from "@/lib/v2";

export type DriverFactStatus = "unselected" | "selected" | "no-evidence";

export interface DriverFacts {
  status: DriverFactStatus;
  driverId: string | null;
  position: string;
  gapToLeader: string;
  gapToAhead: string;
  tyre: string;
  stint: string;
  pitStops: string;
}

const DASH = "—";

/**
 * Seconds gap as +s.sss. Intentional 3-line parity copy of
 * replayMachine.formatGapSeconds: this module stays value-import-free
 * (type-only imports erase under `node --test` type-stripping) so its
 * behavior tests run dependency-free. Parity is pinned by the tests below.
 */
function formatGapSeconds(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `+${value.toFixed(3)}`;
}

function formatGap(
  laps: number | null,
  seconds: number | null,
  valid: boolean | null,
): string {
  if (laps !== null && laps > 0) {
    return `+${laps} LAP${laps > 1 ? "S" : ""}`;
  }
  if (valid === false) return "n/a";
  return formatGapSeconds(seconds);
}

function formatTyre(driver: DriverRaceState): string {
  if (driver.compound === null) return DASH;
  const age = driver.tyre_life !== null ? ` ${driver.tyre_life}` : "";
  const fresh = driver.fresh_tyre === true ? " · new" : "";
  return `${driver.compound.toUpperCase()}${age}${fresh}`;
}

function formatStint(driver: DriverRaceState): string {
  if (driver.stint_number === null) return DASH;
  const lap = driver.stint_lap !== null ? ` · lap ${driver.stint_lap}` : "";
  return `stint ${driver.stint_number}${lap}`;
}

/**
 * Resolves display facts for the workspace-selected driver from the roster
 * already present at the canonical frame. Never fetches, never synthesizes.
 */
export function selectedDriverFacts(
  drivers: DriverRaceState[],
  selectedDriverId: string | null,
): DriverFacts {
  if (selectedDriverId === null) {
    return {
      status: "unselected",
      driverId: null,
      position: DASH,
      gapToLeader: DASH,
      gapToAhead: DASH,
      tyre: DASH,
      stint: DASH,
      pitStops: DASH,
    };
  }
  const driver = drivers.find((d) => d.driver_id === selectedDriverId);
  if (!driver) {
    return {
      status: "no-evidence",
      driverId: selectedDriverId,
      position: DASH,
      gapToLeader: DASH,
      gapToAhead: DASH,
      tyre: DASH,
      stint: DASH,
      pitStops: DASH,
    };
  }
  return {
    status: "selected",
    driverId: driver.driver_id,
    position: driver.position !== null ? `P${driver.position}` : DASH,
    gapToLeader: formatGap(
      driver.gap_to_leader_laps,
      driver.gap_to_leader_s,
      driver.gap_to_leader_valid,
    ),
    gapToAhead: formatGap(
      driver.gap_to_ahead_laps,
      driver.gap_to_ahead_s,
      driver.gap_to_ahead_valid,
    ),
    tyre: formatTyre(driver),
    stint: formatStint(driver),
    pitStops:
      driver.pit_stops_completed_so_far !== null
        ? String(driver.pit_stops_completed_so_far)
        : DASH,
  };
}
