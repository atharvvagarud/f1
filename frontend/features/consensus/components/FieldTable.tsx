// Dense field comparison table (V3.8G).
//
// Semantic table, backend-authoritative values only. Δ = simulation − model
// (+ = simulation higher); ΔRK = simulation_rank − model_rank. Ranks render
// backend average-tie values exactly; ties are never broken for display.
// Rank columns collapse on small viewports; the viewport never overflows.

"use client";

import { useMemo, useState } from "react";
import type { ConsensusDriverRow } from "@/features/consensus/lib/consensusClient";
import {
  compareFieldRows,
  formatDisplacement,
  formatGapPp,
  formatPct,
  formatRank,
  readableConsensusDriver,
  type FieldSortKey,
} from "@/features/consensus/lib/consensusFormat";

const thClass =
  "border-b border-ink-600 px-2 py-2 text-left font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";
const tdClass = "border-b border-ink-700 px-2 py-1.5 font-data text-[12px] tabular-nums";
const tdNumClass = `${tdClass} text-right`;

function SortButton({
  label,
  abbr,
  sortKey,
  activeKey,
  dir,
  onSort,
}: {
  label: string;
  abbr: string;
  sortKey: FieldSortKey;
  activeKey: FieldSortKey | null;
  dir: 1 | -1;
  onSort: (key: FieldSortKey) => void;
}) {
  const active = activeKey === sortKey;
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      aria-label={`Sort by ${label}${active ? ` (${dir === 1 ? "ascending" : "descending"})` : ""}`}
      className="uppercase tracking-[0.14em] hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
    >
      <abbr title={label} className="no-underline">
        {abbr}
      </abbr>
      {active ? <span aria-hidden="true">{dir === 1 ? " ▲" : " ▼"}</span> : null}
    </button>
  );
}

export function FieldTable({
  rows,
  modelRank,
  simulationRank,
  rankDisplacement,
}: {
  rows: ConsensusDriverRow[];
  modelRank: Record<string, number>;
  simulationRank: Record<string, number>;
  rankDisplacement: Record<string, number>;
}) {
  const [sortKey, setSortKey] = useState<FieldSortKey | null>(null);
  const [dir, setDir] = useState<1 | -1>(-1);

  const onSort = (key: FieldSortKey) => {
    if (sortKey === key) {
      setDir(dir === 1 ? -1 : 1);
    } else {
      setSortKey(key);
      setDir(key === "driver" ? 1 : -1);
    }
  };

  const ordered = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => compareFieldRows(a, b, sortKey, dir));
  }, [rows, sortKey, dir]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[330px] border-collapse sm:min-w-[560px]">
        <caption className="sr-only">
          Driver field comparison: model and simulation WIN probabilities,
          signed gap where positive means simulation higher, backend ranks
          and rank displacement
        </caption>
        <thead>
          <tr>
            <th scope="col" className={thClass}>
              <SortButton label="Driver" abbr="Driver" sortKey="driver" activeKey={sortKey} dir={dir} onSort={onSort} />
            </th>
            <th scope="col" className={`${thClass} text-right`}>
              <SortButton label="Model WIN probability" abbr="Model" sortKey="model" activeKey={sortKey} dir={dir} onSort={onSort} />
            </th>
            <th scope="col" className={`${thClass} text-right`}>
              <SortButton label="Simulation WIN frequency" abbr="Sim" sortKey="sim" activeKey={sortKey} dir={dir} onSort={onSort} />
            </th>
            <th scope="col" className={`${thClass} text-right`}>
              <SortButton label="Signed gap, simulation minus model" abbr="Δ" sortKey="gap" activeKey={sortKey} dir={dir} onSort={onSort} />
            </th>
            <th scope="col" className={`${thClass} hidden text-right md:table-cell`}>
              Model rank
            </th>
            <th scope="col" className={`${thClass} hidden text-right md:table-cell`}>
              Sim rank
            </th>
            <th scope="col" className={`${thClass} hidden text-right md:table-cell`}>
              <abbr title="Rank displacement, simulation rank minus model rank" className="no-underline">
                ΔRK
              </abbr>
            </th>
            <th scope="col" className={`${thClass} hidden text-right lg:table-cell`}>
              <abbr title="Finite-simulation sampling range (Wilson 95%)" className="no-underline">
                MC range
              </abbr>
            </th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => {
            const gap = row.signed_gap ?? 0;
            return (
              <tr key={row.driver_id}>
                <th scope="row" className={`${tdClass} font-semibold text-fg`}>
                  {readableConsensusDriver(row.driver_id)}
                </th>
                <td className={tdNumClass}>{formatPct(row.p_model) ?? "—"}</td>
                <td className={tdNumClass}>{formatPct(row.p_simulation) ?? "—"}</td>
                <td className={tdNumClass}>
                  <span aria-label={gap > 0 ? "simulation higher" : gap < 0 ? "model higher" : "equal"}>
                    {formatGapPp(row.signed_gap) ?? "—"}
                  </span>
                </td>
                <td className={`${tdNumClass} hidden md:table-cell`}>
                  {formatRank(modelRank[row.driver_id])}
                </td>
                <td className={`${tdNumClass} hidden md:table-cell`}>
                  {formatRank(simulationRank[row.driver_id])}
                </td>
                <td className={`${tdNumClass} hidden md:table-cell`}>
                  {formatDisplacement(rankDisplacement[row.driver_id] ?? null) ?? "—"}
                </td>
                <td className={`${tdNumClass} hidden text-fg-dim lg:table-cell`}>
                  {row.wilson_95
                    ? `${formatPct(row.wilson_95[0])}–${formatPct(row.wilson_95[1])}`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="px-2 py-2 font-data text-[11px] text-fg-dim">
        Δ = simulation − model (+ simulation higher, − model higher). ΔRK =
        simulation rank − model rank. Ranks are backend average-tie values.
      </p>
    </div>
  );
}
