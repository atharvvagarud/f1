// Factual running order (Phase-5 R5).
//
// Complete roster from RaceState, ordered by factual position (unknown
// positions last). Values pass through verbatim; nulls render as em-dash,
// never zero. Stale vs unobserved drivers are labelled from provenance.

"use client";

import type {
  DriverRaceState,
  ReplayFrameResponse,
} from "@/lib/v2";
import {
  driverStatusOf,
  formatAge,
  formatGapSeconds,
  formatLap,
} from "@/features/replay/lib/replayMachine";

export function readableDriverId(driverId: string): string {
  return driverId.replace(/_/g, " ").toUpperCase();
}

function sortedRoster(drivers: DriverRaceState[]): DriverRaceState[] {
  return [...drivers].sort((a, b) => {
    if (a.position === null && b.position === null) {
      return a.driver_id < b.driver_id ? -1 : 1;
    }
    if (a.position === null) return 1;
    if (b.position === null) return -1;
    return a.position - b.position;
  });
}

function gapCell(driver: DriverRaceState): string {
  if (driver.gap_to_leader_laps !== null && driver.gap_to_leader_laps > 0) {
    return `+${driver.gap_to_leader_laps} LAP${driver.gap_to_leader_laps > 1 ? "S" : ""}`;
  }
  if (driver.gap_to_leader_valid === false) return "n/a";
  return formatGapSeconds(driver.gap_to_leader_s);
}

function tyreCell(driver: DriverRaceState): string {
  if (driver.compound === null) return "—";
  const life = driver.tyre_life !== null ? ` ${driver.tyre_life}` : "";
  const fresh = driver.fresh_tyre === true ? " • new" : "";
  return `${driver.compound.toUpperCase()}${life}${fresh}`;
}

function statusCell(driver: DriverRaceState): { text: string; stale: boolean } {
  const status = driverStatusOf(driver);
  if (status === "unobserved") return { text: "NO DATA", stale: false };
  if (status === "stale") {
    return { text: formatAge(driver.observation_age_s).toUpperCase(), stale: true };
  }
  return { text: "—", stale: false };
}

export function StandingsTable({ frame }: { frame: ReplayFrameResponse }) {
  const drivers = sortedRoster(frame.state.drivers);
  return (
    <section aria-label="Factual running order" className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[13px] tabular-nums">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.12em] text-slate-500">
              <th scope="col" className="px-2 py-2 font-semibold">Pos</th>
              <th scope="col" className="px-2 py-2 font-semibold">Driver</th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">Lap</th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">Gap</th>
              <th scope="col" className="px-2 py-2 font-semibold">Tyre</th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">Stops</th>
              <th scope="col" className="px-2 py-2 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => {
              const status = statusCell(driver);
              const unobserved = !driver.observable;
              return (
                <tr
                  key={driver.driver_id}
                  className={`border-t border-white/5 ${unobserved ? "opacity-45" : ""}`}
                >
                  <td className="px-2 py-1.5 text-slate-200">
                    {driver.position ?? "—"}
                  </td>
                  <td className="px-2 py-1.5">
                    <span className="font-sans font-semibold text-slate-100">
                      {readableDriverId(driver.driver_id)}
                    </span>
                    {driver.driver_number !== null && (
                      <span className="ml-2 text-slate-500">#{driver.driver_number}</span>
                    )}
                    {driver.constructor_id && (
                      <span className="ml-2 text-[11px] uppercase text-slate-500">
                        {driver.constructor_id}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-200">
                    {formatLap(driver.observed_lap_number)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-300">
                    {gapCell(driver)}
                  </td>
                  <td className="px-2 py-1.5 text-slate-300">{tyreCell(driver)}</td>
                  <td className="px-2 py-1.5 text-right text-slate-300">
                    {driver.pit_stops_completed_so_far ?? "—"}
                  </td>
                  <td
                    className={`px-2 py-1.5 text-[11px] font-semibold tracking-wide ${
                      status.stale ? "text-amber-300" : "text-slate-500"
                    }`}
                    title={
                      unobserved
                        ? "No observation at this historical time"
                        : status.stale
                          ? `Last observed ${formatAge(driver.observation_age_s)} — not live`
                          : "Currently observed"
                    }
                  >
                    {status.text}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">
        {frame.state.roster_size} drivers • gaps as observed • stale rows show
        last-known facts, never live values • no retirement is ever inferred
      </p>
    </section>
  );
}
