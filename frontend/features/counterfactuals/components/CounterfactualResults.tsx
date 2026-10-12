// Counterfactual results rendering (V3.7G).
//
// Deliberate hierarchy: primary comparison strip, secondary
// diagnostics, finish distribution, lifecycle evidence, pair
// accounting, source. Backend values render verbatim — this file
// performs no sign flip and no re-derivation. Improvement coloring
// applies only where metric orientation is scientifically defined;
// pit count and lifecycle shares stay neutral.

"use client";

import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";
import type { CounterfactualCompareResponse } from "@/lib/v2";
import {
  INTERVAL_COPY,
  PRIMARY_METRIC_ROWS,
  SECONDARY_METRIC_ROWS,
  SUPERSESSION_COPY,
  deltaFor,
  formatExpectedFinish,
  formatExpectedFinishDelta,
  formatInterval,
  formatPairs,
  formatPitCount,
  formatPositionGainDelta,
  formatProbabilityDelta,
  gainTone,
  lifecycleCounts,
  pointOf,
  supersededShare,
  type MetricRow,
} from "@/features/counterfactuals/lib/counterfactualMachine";

type Tone = "ok" | "warn" | "danger" | "neutral";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  neutral: "text-fg",
};

/** Tone from frozen orientation. Descriptive metrics always neutral. */
function toneFor(row: MetricRow, value: number | null): Tone {
  if (value === null || !Number.isFinite(value) || value === 0) return "neutral";
  if (row.improvement === undefined) return "neutral";
  return value > 0 ? "ok" : "danger";
}

function formatRowValue(row: MetricRow, response: CounterfactualCompareResponse): string {
  const delta = deltaFor(response, row.metric);
  switch (row.kind) {
    case "probability":
      return formatProbabilityDelta(delta);
    case "gain":
      return formatPositionGainDelta(delta);
    case "finish":
      return formatExpectedFinishDelta(delta);
    default:
      return formatProbabilityDelta(delta);
  }
}

function MetricCell({ row, response }: { row: MetricRow; response: CounterfactualCompareResponse }) {
  const delta = deltaFor(response, row.metric);
  const value = pointOf(delta);
  const tone = toneFor(row, value);
  const orientationHint =
    row.kind === "finish"
      ? "Backend BASE − ALT: positive already means ALT improvement."
      : row.kind === "gain"
        ? `Positive = gained positions (${gainTone(value) === "gain" ? "gain" : gainTone(value) === "loss" ? "loss" : "neutral"}).`
        : row.kind === "probability"
          ? "Positive = ALT higher probability."
          : "Descriptive change, not better or worse.";
  return (
    <div className="min-w-0 border border-ink-700 px-3 py-2.5">
      <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">{row.label}</div>
      <div className={`mt-1 font-data text-xl tabular-nums ${TONE_TEXT[tone]}`}>
        {formatRowValue(row, response)}
        <span className="sr-only">{` (${orientationHint})`}</span>
      </div>
      <div className="mt-1 font-data text-[10px] text-fg-dim tabular-nums" title={INTERVAL_COPY}>
        MC 95% {formatInterval(delta)}
      </div>
    </div>
  );
}

function DistributionChart({ response }: { response: CounterfactualCompareResponse }) {
  const refDist = new Map<number, number>();
  for (const bucket of response.base_aggregate?.finish_position_distribution ?? []) {
    refDist.set(bucket.finish_position, bucket.frequency);
  }
  const altDist = new Map<number, number>();
  for (const bucket of response.alternative_aggregate?.finish_position_distribution ?? []) {
    altDist.set(bucket.finish_position, bucket.frequency);
  }
  const positions = [...new Set([...refDist.keys(), ...altDist.keys()])].sort((a, b) => a - b);
  if (positions.length === 0) return null;
  const maxFreq = Math.max(
    0.0001,
    ...positions.map((p) => Math.max(refDist.get(p) ?? 0, altDist.get(p) ?? 0)),
  );
  const baseLabel = response.comparison_form === "PLAN_VS_PLAN" ? "PLAN A" : "REF";
  return (
    <div>
      <svg
        role="img"
        aria-label="Simulated finishing-position distribution for the primary target, base versus alternative. P1 first; mutually exclusive Monte Carlo frequencies."
        viewBox={`0 0 320 ${positions.length * 34 + 4}`}
        className="mt-2 w-full"
      >
        {positions.map((position, index) => {
          const y = index * 34 + 4;
          const ref = refDist.get(position) ?? 0;
          const alt = altDist.get(position) ?? 0;
          return (
            <g key={position}>
              <text x={0} y={y + 10} fill="currentColor" fontSize={10} className="fill-fg-dim">
                {`P${position}`}
              </text>
              <rect x={34} y={y} width={Math.max(1, (ref / maxFreq) * 120)} height={9} className="fill-fg-dim opacity-60" />
              <rect x={34} y={y + 12} width={Math.max(1, (alt / maxFreq) * 120)} height={9} className="fill-signal" />
              <text x={162} y={y + 10} fill="currentColor" fontSize={10} className="fill-fg-muted">
                {`${baseLabel} ${(ref * 100).toFixed(1)}% · ALT ${(alt * 100).toFixed(1)}%`}
              </text>
            </g>
          );
        })}
      </svg>
      <table className="mt-2 w-full border-collapse text-left">
        <caption className="sr-only">
          Simulated finishing-position frequencies, base versus alternative. Mutually exclusive Monte Carlo frequencies.
        </caption>
        <thead>
          <tr className="border-b border-ink-700 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            <th scope="col" className="py-1 pr-3 font-medium">Pos</th>
            <th scope="col" className="py-1 pr-3 font-medium">{baseLabel}</th>
            <th scope="col" className="py-1 pr-3 font-medium">Alt</th>
          </tr>
        </thead>
        <tbody className="font-data text-[12px] tabular-nums">
          {positions.map((position) => (
            <tr key={position} className="border-b border-ink-700/50">
              <th scope="row" className="py-1 pr-3 font-medium text-fg">P{position}</th>
              <td className="py-1 pr-3 text-fg-muted">{((refDist.get(position) ?? 0) * 100).toFixed(1)}%</td>
              <td className="py-1 pr-3 text-fg">{((altDist.get(position) ?? 0) * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CounterfactualResults({ response }: { response: CounterfactualCompareResponse }) {
  const isPlanVsPlan = response.comparison_form === "PLAN_VS_PLAN";
  const base = response.base_aggregate;
  const alt = response.alternative_aggregate;
  const rows = lifecycleCounts(response);
  const altTotal = rows.find((r) => r.arm === "alternative")?.total ?? 0;
  const share = supersededShare(response);
  const primary = response.primary_target_driver_id;
  return (
    <div className="min-w-0 space-y-4">
      <Panel>
        <PanelHeader
          title={isPlanVsPlan ? "Plan A vs plan B" : "No-intervention reference vs plan"}
          meta={`${response.execution_source === "cache" ? "Cached" : "Live"} · 5,000 paired futures`}
          note={
            isPlanVsPlan
              ? "BASE: plan A. ALT: plan B. Positive deltas favor B per each metric's frozen orientation. Plans are never reordered by result."
              : undefined
          }
        />
        <div className="px-4 py-3">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-data text-[11px] uppercase tracking-[0.1em] text-fg-dim">
            <span>
              Base:{" "}
              <span className="text-fg">
                {isPlanVsPlan ? "PLAN A" : "NO-INTERVENTION REFERENCE"}
              </span>
            </span>
            <span>
              Alt: <span className="text-fg">PLAN{response.rival_driver_id ? ` · rival ${readableDriverId(response.rival_driver_id)}` : ""}</span>
            </span>
            <span>
              Target: <span className="text-fg">{primary ? readableDriverId(primary) : "—"}</span>
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" role="list" aria-label="Primary comparison deltas">
            {PRIMARY_METRIC_ROWS.map((row) => (
              <div key={row.metric} role="listitem" className="min-w-0">
                <MetricCell row={row} response={response} />
              </div>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 border-t border-ink-700 pt-3 sm:grid-cols-3">
            {SECONDARY_METRIC_ROWS.map((row) => {
              const delta = deltaFor(response, row.metric);
              const value = pointOf(delta);
              const display =
                row.metric === "delta_pit_count" && value !== null
                  ? `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toFixed(2)}`
                  : formatProbabilityDelta(delta);
              return (
                <div key={row.metric} className="flex min-w-0 items-baseline justify-between gap-3">
                  <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">{row.label}</span>
                  <span className="font-data text-[13px] text-fg tabular-nums">
                    {display}
                    <span className="sr-only">
                      {row.metric === "delta_pit_count" ? " (descriptive; not better or worse)" : " (positive means ALT higher)"}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 border-t border-ink-700 pt-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="min-w-0">
              <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Base expected finish</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">{formatExpectedFinish(base?.expected_finish)}</div>
            </div>
            <div className="min-w-0">
              <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Alt expected finish</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">{formatExpectedFinish(alt?.expected_finish)}</div>
            </div>
            <div className="min-w-0">
              <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Expected pits · base / alt</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatPitCount(base?.expected_pit_count)} / {formatPitCount(alt?.expected_pit_count)}
              </div>
            </div>
            <div className="min-w-0">
              <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Complete pairs</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatPairs(response.complete_pairs, response.requested_pairs)}
              </div>
            </div>
          </div>
          {response.excluded_pairs !== null && response.excluded_pairs > 0 ? (
            <p className="mt-2 font-data text-[11px] text-warn tabular-nums">
              {response.excluded_pairs.toLocaleString("en-US")} requested futures excluded (not valid on both arms).
            </p>
          ) : null}
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Finish distribution"
          meta="Primary target · simulated frequencies"
          note="Target-driver simulated finishing-position distribution, P1 first. Reference/base versus alternative. Backend frequencies verbatim — never reconstructed from quantiles."
        />
        <div className="px-4 py-3">
          <DistributionChart response={response} />
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Intervention lifecycle"
          meta="Did the schedule actually execute?"
          note="What happened to scheduled interventions across simulated futures. Supersession is not failure."
        />
        <div className="px-4 py-3">
          {rows.length === 0 ? (
            <p className="font-data text-[12px] text-fg-dim">No lifecycle evidence returned.</p>
          ) : (
            <ul className="space-y-2">
              {rows.map((row) => (
                <li key={`${row.arm}-${row.status}`}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 font-data text-[11px] tabular-nums">
                    <span className="uppercase tracking-[0.1em] text-fg-muted">
                      {row.arm} · {row.status}
                    </span>
                    <span className="text-fg">
                      {row.count.toLocaleString("en-US")} · {(row.share * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div
                    role="img"
                    aria-label={`${row.arm} ${row.status}: ${row.count} of ${row.total} simulated futures`}
                    className="mt-1 h-1.5 w-full bg-ink-850"
                  >
                    <div
                      className={`h-full ${row.status === "EXECUTED" ? "bg-ok" : row.status === "SUPERSEDED" ? "bg-warn" : "bg-fg-dim"}`}
                      style={{ width: `${Math.max(row.share * 100, row.count > 0 ? 0.5 : 0)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {share !== null && share > 0 ? (
            <p className="mt-3 max-w-2xl text-[12px] leading-5 text-fg-muted">
              {(share * 100).toFixed(1)}% of scheduled alternative interventions were
              superseded by an earlier simulator-generated pit event. {SUPERSESSION_COPY}
            </p>
          ) : null}
          <p className="mt-2 font-data text-[11px] text-fg-dim tabular-nums">
            {altTotal.toLocaleString("en-US")} scheduled alternative events across {response.complete_pairs?.toLocaleString("en-US") ?? "—"} complete pairs.
          </p>
        </div>
      </Panel>

      <div className="border border-ink-700 bg-ink-900 px-4 py-3">
        <SemanticsNote>
          Simulated differences under a controlled intervention — not historical
          truth, not a recommendation, not an optimal strategy. Cache holds the
          same validated 5,000-future result as a live run.
        </SemanticsNote>
      </div>
    </div>
  );
}
