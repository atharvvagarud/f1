// Simulated finishing-position distribution (Phase-6 R8; UI4).
//
// A driver × finishing-position matrix over the actual aggregate. Every cell is
// the empirical % of valid simulated trials in which that driver finished in
// that position — actual frequencies only, no smoothing, no interpolated
// positions. The number is the value; the neutral intensity step is a redundant
// cue, never the sole carrier of meaning. A real table gives screen readers the
// driver row and position column for every cell.

"use client";

import { useMemo } from "react";
import type { SimulationResponse } from "@/lib/v2";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import {
  distributionLevel,
  distributionPositions,
  formatDistributionCell,
  sortDriversByExpectedFinish,
} from "@/features/simulator/lib/simulatorMachine";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";

const LEVEL_BG: Record<0 | 1 | 2 | 3, string> = {
  0: "",
  1: "bg-ink-850",
  2: "bg-ink-700",
  3: "bg-ink-600",
};

export function PositionDistribution({
  response,
}: {
  response: SimulationResponse;
}) {
  const drivers = useMemo(
    () => sortDriversByExpectedFinish(response.drivers),
    [response.drivers],
  );
  const positions = useMemo(
    () => distributionPositions(response.drivers),
    [response.drivers],
  );

  if (drivers.length === 0 || positions.length === 0) return null;

  const columnLabel = (position: number | null) =>
    position === null ? "DNF" : `P${position}`;

  return (
    <Panel>
      <PanelHeader
        title="Finishing-position distribution"
        meta={`${drivers.length} drivers × ${positions.length} positions · scroll → for positions`}
        note="Each cell is the % of valid simulated trials in which the driver finished in that position. Rows are ordered by expected finish (best first); blank = 0%. Empirical frequencies only — no smoothing or interpolation."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-[11px]">
          <caption className="sr-only">
            Simulated finishing-position distribution. Rows are drivers, columns
            are finishing positions, each cell is the percentage of valid
            simulated trials.
          </caption>
          <thead>
            <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              <th
                scope="col"
                className="sticky left-0 z-10 bg-ink-900 px-3 py-2 text-left font-medium"
              >
                Driver
              </th>
              {positions.map((position) => (
                <th
                  key={String(position)}
                  scope="col"
                  className="px-1 py-2 text-right font-medium"
                >
                  {columnLabel(position)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => {
              const byPosition = new Map(
                driver.finish_position_distribution.map((bucket) => [
                  bucket.position,
                  bucket.frequency,
                ]),
              );
              return (
                <tr
                  key={driver.driver_id}
                  className="border-t border-ink-700 hover:bg-ink-850/60"
                >
                  <th
                    scope="row"
                    className="sticky left-0 z-10 bg-ink-900 px-3 py-1.5 text-left font-data text-[11px] font-normal uppercase tracking-[0.04em] text-fg"
                  >
                    {readableDriverId(driver.driver_id)}
                  </th>
                  {positions.map((position) => {
                    const frequency = byPosition.get(position) ?? 0;
                    return (
                      <td
                        key={String(position)}
                        className={`px-1 py-1.5 text-right font-data text-fg tabular-nums ${LEVEL_BG[distributionLevel(frequency)]}`}
                        title={`${columnLabel(position)} · ${(frequency * 100).toFixed(2)}%`}
                      >
                        {formatDistributionCell(frequency)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="border-t border-ink-700 bg-ink-950/50 px-4 py-3">
        <SemanticsNote>
          Frequencies are MONTE_CARLO_FREQUENCY outcomes over valid simulated
          trials; each trial produces one mutually exclusive finishing order, so
          each row sums to 100% across positions. Cell shading is a redundant
          intensity cue — the number is the value.
        </SemanticsNote>
      </div>
    </Panel>
  );
}
