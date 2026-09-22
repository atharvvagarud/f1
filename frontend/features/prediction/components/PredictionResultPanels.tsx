"use client";

// Field / checkpoint / trend result panels (UI2). Dense, ruled, tabular —
// timing-tower structure instead of one bordered card per number. All values
// are API-provided; rank is the model's own ordering of its top drivers.

import { Fragment } from "react";
import ProbabilityChart from "@/components/prediction/ProbabilityChart";
import {
  formatDriverName,
  formatGap,
  formatPercent,
  formatWhole,
  titleCaseModelName,
} from "@/lib/predictionHelpers";
import type { ChartPoint, PredictionView } from "../lib/predictionTransforms";
import {
  Panel,
  PanelHeader,
  ProbabilityBar,
  SemanticsNote,
} from "./PredictionPrimitives";

function rankLabel(value: number | null) {
  return value ? `P${value}` : "—";
}

export function PredictionField({ view }: { view: PredictionView }) {
  return (
    <Panel>
      <PanelHeader
        title="Field — win probability by model"
        meta={`Lap ${view.leader.lap}`}
        note="Each model ranks the field by its own independent binary win probability. Rank is the model's ordering, not the race order."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[13px]">
          <caption className="sr-only">
            Win probability by model. Each model groups its ranked drivers; each
            row is a driver with that model&apos;s independent binary win
            probability, race position, gap, compound and tyre life.
          </caption>
          <thead>
            <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <th scope="col" className="px-3 py-2 font-medium">#</th>
              <th scope="col" className="px-3 py-2 font-medium">Driver</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Win probability
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Pos</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Gap</th>
              <th scope="col" className="px-3 py-2 font-medium">Compound</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Tyre life</th>
            </tr>
          </thead>
          <tbody>
            {view.field.map((group) => (
              <Fragment key={group.modelKey}>
                <tr className="border-t-2 border-ink-600 bg-ink-850">
                  <th
                    scope="colgroup"
                    colSpan={7}
                    className="px-3 py-1.5 text-left font-display text-[11px] font-bold uppercase tracking-[0.14em] text-fg-muted"
                  >
                    {titleCaseModelName(group.modelKey)}
                  </th>
                </tr>
                {group.drivers.map((driver, index) => (
                  <tr
                    key={`${group.modelKey}-${driver.driver}`}
                    className="border-t border-ink-700 hover:bg-ink-850/60"
                  >
                    <td className="px-3 py-2 font-data text-fg-dim tabular-nums">
                      {index + 1}
                    </td>
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      <span className="text-fg">
                        {formatDriverName(driver.driver)}
                      </span>
                      <span className="ml-2 font-data text-[11px] text-fg-dim">
                        #{formatWhole(driver.driver_number)}
                      </span>
                    </th>
                    <td className="px-3 py-2">
                      <span className="flex items-center justify-end gap-2">
                        <ProbabilityBar
                          value={driver.win_probability}
                          className="w-16"
                        />
                        <span className="w-14 text-right font-data text-fg tabular-nums">
                          {formatPercent(driver.win_probability)}
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                      {rankLabel(driver.position_x)}
                    </td>
                    <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                      {formatGap(driver.gap_to_leader_seconds)}
                    </td>
                    <td className="px-3 py-2 text-fg-muted">
                      {driver.compound_x || "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                      {formatWhole(driver.tyre_life_x)}
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function PredictionCheckpoints({ view }: { view: PredictionView }) {
  const showModel = view.mode === "ensemble";

  return (
    <Panel>
      <PanelHeader
        title="Checkpoint detail"
        meta={showModel ? "3 models · by lap" : view.modeLabel}
        note="Every row is one recorded model checkpoint. Probabilities are the model's independent binary estimate for the predicted driver at that lap."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px] text-left text-[13px]">
          <caption className="sr-only">
            Checkpoint detail. Each row is one recorded model checkpoint with the
            predicted winner, its win probability and the official actual
            winner and finish.
          </caption>
          <thead>
            <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <th scope="col" className="px-3 py-2 font-medium">Lap</th>
              {showModel ? (
                <th scope="col" className="px-3 py-2 font-medium">Model</th>
              ) : null}
              <th scope="col" className="px-3 py-2 font-medium">Predicted winner</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Win prob</th>
              <th scope="col" className="px-3 py-2 font-medium">Actual winner</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Actual finish
              </th>
            </tr>
          </thead>
          <tbody>
            {view.checkpoints.map((row, index) => {
              const newLap =
                index > 0 && view.checkpoints[index - 1].lap !== row.lap;
              return (
                <tr
                  key={`${row.lap}-${row.modelKey}-${index}`}
                  className={`border-t border-ink-700 hover:bg-ink-850/60 ${
                    newLap ? "border-t-2 border-ink-600" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-data text-fg-muted tabular-nums">
                    {row.lap}
                  </td>
                  {showModel ? (
                    <td className="px-3 py-2 text-fg-muted">
                      {titleCaseModelName(row.modelKey)}
                    </td>
                  ) : null}
                  <td className="px-3 py-2 text-fg">
                    {formatDriverName(row.predictedWinner)}
                  </td>
                  <td className="px-3 py-2 text-right font-data text-fg tabular-nums">
                    {formatPercent(row.winProbability)}
                  </td>
                  <td className="px-3 py-2 text-fg-muted">
                    {formatDriverName(row.actualWinner)}
                  </td>
                  <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                    {rankLabel(row.actualRank)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function PredictionTrend({
  chartRows,
  meta,
}: {
  chartRows: Record<string, ChartPoint[]>;
  meta: string;
}) {
  return (
    <Panel>
      <PanelHeader
        title="Win probability by checkpoint"
        meta={meta}
        note="Series are separated by line weight, dash pattern and marker shape, not colour alone. Values break at checkpoints the model did not evaluate."
      />
      <div className="px-4 py-4">
        <ProbabilityChart groupedData={chartRows} />
        <div className="mt-3 border-t border-ink-700 pt-3">
          <SemanticsNote>
            Each series is one model&apos;s independent binary win probability
            for its predicted driver at each checkpoint — not a normalised race
            share.
          </SemanticsNote>
        </div>
      </div>
    </Panel>
  );
}
