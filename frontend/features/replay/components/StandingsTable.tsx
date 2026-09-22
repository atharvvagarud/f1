// Factual running order (Phase-5 R5; UI3 dense timing-tower table).
//
// Complete roster from RaceState, ordered by factual position (unknown
// positions last). Values pass through verbatim; nulls render as em-dash,
// never zero. Stale vs unobserved drivers are labelled from provenance.
// No per-driver cards; one hairline-ruled row per driver, tabular numerals.

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

function TyreCell({ driver }: { driver: DriverRaceState }) {
  if (driver.compound === null) {
    return <span className="text-fg-dim">—</span>;
  }
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className="rounded-chip border border-ink-700 bg-ink-850 px-1.5 py-0.5 font-ui text-[10px] uppercase tracking-[0.08em] text-fg-muted">
        {driver.compound.toUpperCase()}
      </span>
      {driver.tyre_life !== null ? (
        <span className="text-[12px] tabular-nums text-fg-muted">
          {driver.tyre_life}
        </span>
      ) : (
        <span className="text-fg-dim">—</span>
      )}
      {driver.fresh_tyre === true ? (
        <span className="font-ui text-[10px] uppercase tracking-[0.08em] text-fg-dim">
          new
        </span>
      ) : null}
    </span>
  );
}

function statusCell(driver: DriverRaceState): { text: string; tone: string } {
  const status = driverStatusOf(driver);
  if (status === "unobserved") {
    return { text: "NO DATA", tone: "text-fg-dim" };
  }
  if (status === "stale") {
    return {
      text: formatAge(driver.observation_age_s).toUpperCase(),
      tone: "text-warn",
    };
  }
  return { text: "AT T", tone: "text-fg-dim" };
}

export function StandingsTable({ frame }: { frame: ReplayFrameResponse }) {
  const drivers = sortedRoster(frame.state.drivers);
  return (
    <section aria-label="Factual running order" className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse font-data text-[12px] tabular-nums">
          <caption className="sr-only">
            Factual running order at this replay frame. Each row is one driver;
            columns are position, driver, observed lap, gap, tyre, pit stops and
            observation status.
          </caption>
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850 text-left font-ui text-[10px] uppercase tracking-[0.12em] text-fg-dim">
              <th scope="col" className="w-12 px-2 py-2 text-right font-semibold">
                Pos
              </th>
              <th scope="col" className="px-2 py-2 font-semibold">
                Driver
              </th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">
                Lap
              </th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">
                Gap
              </th>
              <th scope="col" className="px-2 py-2 font-semibold">
                Tyre
              </th>
              <th scope="col" className="w-14 px-2 py-2 text-right font-semibold">
                Pit
              </th>
              <th scope="col" className="px-2 py-2 font-semibold">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => {
              const status = statusCell(driver);
              const unobserved = !driver.observable;
              return (
                <tr
                  key={driver.driver_id}
                  className={`border-b border-ink-700 ${
                    unobserved ? "text-fg-dim" : "text-fg"
                  }`}
                >
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {driver.position ?? "—"}
                  </td>
                  <th
                    scope="row"
                    className="px-2 py-1.5 text-left font-normal"
                  >
                    <span className="font-ui text-[12px] font-semibold whitespace-nowrap text-fg">
                      {readableDriverId(driver.driver_id)}
                    </span>
                    {driver.driver_number !== null ? (
                      <span className="ml-2 text-fg-dim">
                        #{driver.driver_number}
                      </span>
                    ) : null}
                    {driver.constructor_id ? (
                      <span className="ml-2 font-ui text-[10px] uppercase tracking-[0.08em] text-fg-dim">
                        {driver.constructor_id}
                      </span>
                    ) : null}
                  </th>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {formatLap(driver.observed_lap_number)}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {gapCell(driver)}
                  </td>
                  <td className="px-2 py-1.5">
                    <TyreCell driver={driver} />
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {driver.pit_stops_completed_so_far ?? "—"}
                  </td>
                  <td
                    className={`px-2 py-1.5 font-ui text-[10px] font-semibold uppercase tracking-[0.08em] whitespace-nowrap ${status.tone}`}
                    title={
                      unobserved
                        ? "No observation at this historical time"
                        : status.text === "AT T"
                          ? "Observed at this state's historical time"
                          : `Last observed ${formatAge(driver.observation_age_s)} before this state — not live`
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
      <p className="border-t border-ink-700 px-3 py-2 font-data text-[10px] leading-4 text-fg-dim">
        {frame.state.roster_size} drivers · gaps as observed · stale rows show
        last-known facts, never live values · no retirement is ever inferred
      </p>
    </section>
  );
}
