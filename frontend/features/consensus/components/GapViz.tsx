// Paired probability comparison (V3.8G).
//
// One dumbbell row per driver: MODEL marker (outlined square) and SIM
// marker (filled disc) positioned on a shared 0–100% native-probability
// scale. Endpoints are shape- plus label-encoded, never color-only. The two
// values are never combined and nothing is drawn between them. Values render
// as text beside every marker, so position is never the sole carrier.

"use client";

import type { ConsensusDriverRow } from "@/features/consensus/lib/consensusClient";
import {
  formatPct,
  readableConsensusDriver,
} from "@/features/consensus/lib/consensusFormat";

function markerLeft(p: number): string {
  const safe = Number.isFinite(p) ? Math.max(0, Math.min(1, p)) : 0;
  return `${(safe * 100).toFixed(1)}%`;
}

export function GapViz({ rows }: { rows: ConsensusDriverRow[] }) {
  const ordered = [...rows].sort(
    (a, b) => (b.p_model ?? -1) - (a.p_model ?? -1),
  );
  return (
    <div>
      <div className="flex items-center gap-4 px-2 pb-2 font-data text-[10px] uppercase tracking-[0.14em] text-fg-dim" aria-hidden="true">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 border border-fg" />
          Model
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-fg" />
          Sim
        </span>
        <span className="ml-auto">0% native → 100% native</span>
      </div>
      <ul className="divide-y divide-ink-700">
        {ordered.map((row) => {
          const pm = row.p_model ?? 0;
          const ps = row.p_simulation ?? 0;
          const lo = Math.min(pm, ps);
          const hi = Math.max(pm, ps);
          return (
            <li
              key={row.driver_id}
              className="grid grid-cols-[110px_1fr] items-center gap-2 px-2 py-1 sm:grid-cols-[150px_1fr]"
            >
              <span className="truncate font-data text-[11px] text-fg">
                {readableConsensusDriver(row.driver_id)}
              </span>
              <span
                className="relative block h-7"
                role="img"
                aria-label={`${readableConsensusDriver(row.driver_id)}: model ${formatPct(row.p_model) ?? "unavailable"}, simulation ${formatPct(row.p_simulation) ?? "unavailable"}`}
              >
                <span aria-hidden="true" className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-ink-600" />
                <span
                  aria-hidden="true"
                  className="absolute top-1/2 h-px -translate-y-1/2 bg-fg-dim"
                  style={{ left: markerLeft(lo), width: `calc(${markerLeft(hi)} - ${markerLeft(lo)})` }}
                />
                <span
                  aria-hidden="true"
                  title={`Model ${formatPct(row.p_model) ?? "—"}`}
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 border border-fg bg-ink-900"
                  style={{ left: markerLeft(pm) }}
                />
                <span
                  aria-hidden="true"
                  title={`Simulation ${formatPct(row.p_simulation) ?? "—"}`}
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-fg"
                  style={{ left: markerLeft(ps) }}
                />
                <span className="absolute top-1/2 hidden -translate-y-1/2 font-data text-[10px] tabular-nums text-fg-dim sm:block" style={{ left: `calc(${markerLeft(Math.max(pm, ps))} + 10px)` }}>
                  {formatGapPpSigned(row.signed_gap)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="px-2 py-2 font-data text-[11px] text-fg-dim">
        Native probabilities on one 0–100% scale for visual comparison only.
        Model and simulation values come from different probability families.
      </p>
    </div>
  );
}

function formatGapPpSigned(gap: number | null): string {
  if (gap === null || !Number.isFinite(gap)) return "—";
  const pp = gap * 100;
  if (Math.abs(pp) < 0.05) return "0.0";
  const sign = pp > 0 ? "+" : "−";
  return `${sign}${Math.abs(pp).toFixed(1)}`;
}
