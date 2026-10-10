// Strategy 2.0 comparison results (V3.6G).
//
// Presentation only: the backend owns every estimate, interval, leader
// and execution rate. Reference is the simulated no-intervention run
// (never STAY OUT, never a team plan). Leaders are point-estimate
// labels, never recommendations; objectives may disagree and there is
// no single preferred alternative. Deltas keep backend orientation:
// positive = improvement, including expected finish.

"use client";

import Link from "next/link";
import { Panel, PanelHeader, ProbabilityBar, SemanticsNote } from "@/components/ui/Panel";
import type {
  Strategy2AlternativeResult,
  Strategy2CompareResponse,
} from "@/lib/v2";
import {
  formatDeltaPoints,
  formatDeltaPositions,
  formatFinish,
  formatProbability,
  formatSamplingInterval,
  formatStrategyCount,
} from "@/features/strategy/lib/strategyMachine";
import {
  CACHE_MISS_COPY,
  DOWNSIDE_COPY,
  INERT_COPY,
  INTERVAL_COPY,
  LEADER_COPY,
  REFERENCE_COPY,
  STRATEGY2_LEADER_LABELS,
  STRATEGY2_TRADE_OFF_ROWS,
  SUPERSEDED_COPY,
  aggregateFor,
  deltaFor,
  formatDownside,
  formatPairs,
  leadsFor,
} from "@/features/strategy/lib/strategy2Machine";

const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

function deltaText(metric: string, value: number | null): string {
  if (metric === "delta_expected_finish") return formatDeltaPositions(value);
  if (metric === "delta_downside_probability") return formatDownside(value);
  return formatDeltaPoints(value);
}

function valueText(metric: string, value: number | null): string {
  if (metric === "delta_expected_finish") return formatFinish(value);
  if (metric === "delta_downside_probability") return formatDownside(value);
  return formatProbability(value);
}

function intervalText(
  metric: string,
  low: number | null,
  high: number | null,
): string {
  if (low === null || high === null) return "interval withheld";
  if (metric === "delta_expected_finish") {
    return `${formatDeltaPositions(low)} to ${formatDeltaPositions(high)}`;
  }
  if (metric === "delta_downside_probability") {
    return `${formatDownside(low)} to ${formatDownside(high)}`;
  }
  return formatSamplingInterval(low, high, false);
}

function DeltaCell({
  alternative,
  metric,
}: {
  alternative: Strategy2AlternativeResult;
  metric: string;
}) {
  if (!alternative.evaluated) {
    return <span className="text-fg-dim">—</span>;
  }
  const delta = deltaFor(alternative, metric);
  if (!delta) return <span className="text-fg-dim">—</span>;
  const altValue =
    metric === "delta_downside_probability"
      ? delta.point_estimate
      : aggregateFor(alternative, metric, "alternative");
  return (
    <span className="block">
      <span className="block text-fg">{valueText(metric, altValue)}</span>
      {metric === "delta_downside_probability" ? null : (
        <span className="mt-0.5 block text-fg-muted">
          {deltaText(metric, delta.point_estimate)}
        </span>
      )}
      <span className="mt-0.5 block text-[11px] text-fg-dim">
        [{intervalText(metric, delta.ci_low, delta.ci_high)}]
      </span>
      {delta.availability !== "AVAILABLE" ? (
        <span className="mt-0.5 block text-[11px] text-warn">
          {delta.valid_pairs} pairs
        </span>
      ) : null}
    </span>
  );
}

function LeadsChips({ candidateKey, leaders }: { candidateKey: string; leaders: Record<string, string | null> }) {
  const led = leadsFor(candidateKey, leaders);
  if (led.length === 0) return null;
  return (
    <span className="mt-1 block">
      <span className="font-ui text-[9px] uppercase tracking-[0.14em] text-fg-dim">
        Leads on{" "}
      </span>
      <span className="font-data text-[11px] text-fg">
        {led.map((k) => STRATEGY2_LEADER_LABELS[k]).join(" · ")}
      </span>
    </span>
  );
}

function DistributionChart({
  response,
  selected,
}: {
  response: Strategy2CompareResponse;
  selected: Strategy2AlternativeResult;
}) {
  const refDist = new Map<number, number>();
  for (const bucket of selected.reference_aggregate?.finish_position_distribution ?? []) {
    if (bucket.position !== null) refDist.set(bucket.position, bucket.frequency);
  }
  const altDist = new Map<number, number>();
  for (const bucket of selected.alternative_aggregate?.finish_position_distribution ?? []) {
    if (bucket.position !== null) altDist.set(bucket.position, bucket.frequency);
  }
  const positions = [...new Set([...refDist.keys(), ...altDist.keys()])].sort(
    (a, b) => a - b,
  );
  if (positions.length === 0) {
    return (
      <p className="mt-2 text-[12px] text-fg-dim">
        No distribution: alternative was not evaluated
        {selected.reason ? ` (${selected.reason})` : ""}.
      </p>
    );
  }
  const maxFreq = Math.max(
    0.0001,
    ...positions.map((p) => Math.max(refDist.get(p) ?? 0, altDist.get(p) ?? 0)),
  );
  return (
    <div>
      <svg
        role="img"
        aria-label={`Simulated finishing-position distribution for the target driver, reference versus ${selected.candidate_key}. Reference and alternative frequencies per position.`}
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
              <rect
                x={34}
                y={y}
                width={Math.max(1, (ref / maxFreq) * 120)}
                height={9}
                className="fill-fg-dim opacity-60"
              />
              <rect
                x={34}
                y={y + 12}
                width={Math.max(1, (alt / maxFreq) * 120)}
                height={9}
                className="fill-signal"
              />
              <text x={162} y={y + 10} fill="currentColor" fontSize={10} className="fill-fg-muted">
                {`REF ${formatProbability(ref)} · ALT ${formatProbability(alt)}`}
              </text>
            </g>
          );
        })}
      </svg>
      <table className="mt-2 w-full border-collapse text-left">
        <caption className="sr-only">
          Simulated finishing-position frequencies, reference versus selected
          alternative. Mutually exclusive Monte Carlo frequencies.
        </caption>
        <thead>
          <tr className="border-b border-ink-700 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            <th scope="col" className="py-1 pr-3 font-medium">Pos</th>
            <th scope="col" className="py-1 pr-3 font-medium">Reference</th>
            <th scope="col" className="py-1 font-medium">{selected.candidate_key}</th>
          </tr>
        </thead>
        <tbody className="font-data text-[12px] tabular-nums text-fg">
          {positions.map((position) => (
            <tr key={position} className="border-b border-ink-700">
              <th scope="row" className="py-1 pr-3 font-normal">P{position}</th>
              <td className="py-1 pr-3">{formatProbability(refDist.get(position) ?? 0)}</td>
              <td className="py-1">{formatProbability(altDist.get(position) ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 font-data text-[11px] text-fg-dim">
        Target {response.target_driver_id} · mutually exclusive simulated
        frequencies · reference and alternative share paired futures where valid.
      </p>
    </div>
  );
}

function truncateIdentity(value: string): string {
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value;
}

export function Strategy2Results({
  response,
  detailKey,
  onSelectDetail,
}: {
  response: Strategy2CompareResponse;
  detailKey: string | null;
  onSelectDetail: (key: string) => void;
}) {
  const evaluated = response.alternatives.filter((a) => a.evaluated);
  const selected =
    response.alternatives.find((a) => a.candidate_key === detailKey) ??
    evaluated[0] ??
    response.alternatives[0];
  const provenance = response.provenance as Record<string, string | number | null>;

  return (
    <div className="mt-4 space-y-4">
      <Panel>
        <PanelHeader
          title="Simulated no-intervention reference"
          meta={`${formatStrategyCount(response.simulation_count)} paired futures · seed ${response.master_seed}`}
          note={REFERENCE_COPY}
        />
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-3 lg:grid-cols-6">
          {evaluated[0]?.reference_aggregate ? (
            <>
              <div className="min-w-0">
                <div className={labelClass}>Win frequency</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatProbability(evaluated[0].reference_aggregate.win_frequency)}
                </div>
              </div>
              <div className="min-w-0">
                <div className={labelClass}>Podium frequency</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatProbability(evaluated[0].reference_aggregate.podium_frequency)}
                </div>
              </div>
              <div className="min-w-0">
                <div className={labelClass}>Top 5 frequency</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatProbability(evaluated[0].reference_aggregate.top5_frequency)}
                </div>
              </div>
              <div className="min-w-0">
                <div className={labelClass}>Top 10 frequency</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatProbability(evaluated[0].reference_aggregate.top10_frequency)}
                </div>
              </div>
              <div className="min-w-0">
                <div className={labelClass}>Expected finish</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatFinish(evaluated[0].reference_aggregate.expected_finish)}
                </div>
              </div>
              <div className="min-w-0">
                <div className={labelClass}>Complete pairs</div>
                <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                  {formatStrategyCount(evaluated[0].complete_pairs)}
                </div>
              </div>
            </>
          ) : (
            <p className="col-span-full text-[13px] text-fg-dim">
              No evaluated alternative; reference aggregates unavailable.
            </p>
          )}
        </div>
        <div className="border-t border-ink-700 px-4 py-2">
          <p className="font-data text-[11px] uppercase tracking-[0.1em] text-warn">
            No intervention ≠ stay out: stay out is a modelled alternative below.
          </p>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Objective leaders"
          meta="Point estimates only"
          note={LEADER_COPY}
        />
        <div className="flex flex-wrap gap-x-6 gap-y-2 px-4 py-3">
          {Object.entries(STRATEGY2_LEADER_LABELS).map(([leaderKey, label]) => (
            <div key={leaderKey} className="min-w-0">
              <div className={labelClass}>{label}</div>
              <div className="mt-1 font-data text-[12px] font-bold text-fg">
                {response.leaders[leaderKey] ?? "—"}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Outcome trade-offs"
          meta="Alternative value · simulated difference · 95% MC interval"
          note="Simulated comparison. Deltas are paired differences against the shared no-intervention reference; positive means the alternative improved the estimate. Expected-finish deltas are reference minus alternative in positions."
        />
        <div className="hidden overflow-x-auto lg:block">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">
              Outcome trade-off matrix: reference aggregates and per-alternative
              simulated differences with 95% Monte Carlo intervals.
            </caption>
            <thead>
              <tr className="border-b-2 border-ink-600 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                <th scope="col" className="sticky left-0 bg-ink-900 px-4 py-2 font-medium">
                  Outcome
                </th>
                <th scope="col" className="min-w-36 px-4 py-2 font-medium">
                  Reference ·<br />no intervention
                </th>
                {response.alternatives.map((alt) => (
                  <th scope="col" key={alt.candidate_key} className="min-w-36 px-4 py-2 font-medium">
                    {alt.candidate_key}
                    {!alt.evaluated ? (
                      <span className="block text-[10px] font-normal normal-case tracking-normal text-fg-dim">
                        not evaluated · {alt.reason ?? "invalid"}
                      </span>
                    ) : null}
                    <LeadsChips candidateKey={alt.candidate_key} leaders={response.leaders} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-data text-[12px] tabular-nums">
              {STRATEGY2_TRADE_OFF_ROWS.map((row) => (
                <tr key={row.metric} className="border-b border-ink-700 text-fg">
                  <th scope="row" className="sticky left-0 bg-ink-900 px-4 py-2 font-semibold">
                    {row.label}
                    <span className="block text-[10px] font-normal text-fg-dim">
                      {row.kind === "probability"
                        ? "frequency · Δ in pp"
                        : row.kind === "position"
                          ? "positions · Δ ref − alt"
                          : "paired share worse"}
                    </span>
                  </th>
                  <td className="px-4 py-2">
                    {row.metric === "delta_downside_probability" ? (
                      <span className="text-fg-dim">—</span>
                    ) : (
                      valueText(
                        row.metric,
                        evaluated[0]
                          ? aggregateFor(evaluated[0], row.metric, "reference")
                          : null,
                      )
                    )}
                  </td>
                  {response.alternatives.map((alt) => (
                    <td key={alt.candidate_key} className="px-4 py-2 align-top">
                      <DeltaCell alternative={alt} metric={row.metric} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 lg:hidden">
          <label htmlFor="strategy2-mobile-alt" className={labelClass}>
            Alternative
          </label>
          <select
            id="strategy2-mobile-alt"
            value={selected?.candidate_key ?? ""}
            onChange={(event) => onSelectDetail(event.target.value)}
            className="mt-1.5 h-9 w-full border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg focus-visible:outline-2 focus-visible:outline-focus"
          >
            {response.alternatives.map((alt) => (
              <option key={alt.candidate_key} value={alt.candidate_key}>
                {alt.candidate_key}
              </option>
            ))}
          </select>
          {selected ? (
            <table className="mt-3 w-full border-collapse text-left">
              <caption className="sr-only">
                Outcome rows for {selected.candidate_key}: reference, alternative
                value, simulated difference and 95% Monte Carlo interval.
              </caption>
              <thead>
                <tr className="border-b border-ink-700 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                  <th scope="col" className="py-1 pr-2 font-medium">Outcome</th>
                  <th scope="col" className="py-1 pr-2 font-medium">Ref</th>
                  <th scope="col" className="py-1 font-medium">Alt · Δ · interval</th>
                </tr>
              </thead>
              <tbody className="font-data text-[12px] tabular-nums text-fg">
                {STRATEGY2_TRADE_OFF_ROWS.map((row) => (
                  <tr key={row.metric} className="border-b border-ink-700">
                    <th scope="row" className="py-2 pr-2 align-top font-semibold">
                      {row.short}
                    </th>
                    <td className="py-2 pr-2 align-top">
                      {row.metric === "delta_downside_probability"
                        ? "—"
                        : valueText(
                            row.metric,
                            evaluated[0]
                              ? aggregateFor(evaluated[0], row.metric, "reference")
                              : null,
                          )}
                    </td>
                    <td className="py-2 align-top">
                      <DeltaCell alternative={selected} metric={row.metric} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <LeadsChips
            candidateKey={selected?.candidate_key ?? ""}
            leaders={response.leaders}
          />
        </div>
        <div className="border-t border-ink-700 px-4 py-3">
          <SemanticsNote>
            95% MC interval: {INTERVAL_COPY} Downside: {DOWNSIDE_COPY}
          </SemanticsNote>
        </div>
      </Panel>

      {selected ? (
        <Panel>
          <PanelHeader
            title="Position distribution · detail"
            meta="Reference versus one alternative"
            note="Target-driver simulated finishing-position distribution. Mutually exclusive Monte Carlo frequencies, positions ordered P1 onward."
          />
          <div className="border-b border-ink-700 px-4 py-3">
            <label htmlFor="strategy2-detail-alt" className={labelClass}>
              Detailed alternative
            </label>
            <select
              id="strategy2-detail-alt"
              value={selected.candidate_key}
              onChange={(event) => onSelectDetail(event.target.value)}
              className="mt-1.5 h-9 w-full max-w-md border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg focus-visible:outline-2 focus-visible:outline-focus"
            >
              {response.alternatives.map((alt) => (
                <option key={alt.candidate_key} value={alt.candidate_key}>
                  {alt.candidate_key}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-2">
            <div className="min-w-0">
              <DistributionChart response={response} selected={selected} />
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Execution diagnostics</div>
              {selected.execution ? (
                <dl className="mt-2 space-y-1 font-data text-[12px] tabular-nums text-fg">
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Requested futures</dt>
                    <dd>{formatStrategyCount(selected.requested_pairs)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Complete pairs</dt>
                    <dd>{formatStrategyCount(selected.complete_pairs)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Excluded pairs</dt>
                    <dd>{formatStrategyCount(selected.excluded_pairs)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Executed</dt>
                    <dd>{(selected.execution.applied_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Inert</dt>
                    <dd>{(selected.execution.inert_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Superseded</dt>
                    <dd>{(selected.execution.superseded_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Not executed</dt>
                    <dd>{(selected.execution.suppressed_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Race-end cancelled</dt>
                    <dd>{(selected.execution.race_end_cancelled_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Baseline pit suppressed</dt>
                    <dd>{selected.execution.baseline_pit_suppressed}</dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-2 text-[12px] text-fg-dim">
                  No execution data: alternative was not evaluated
                  {selected.reason ? ` (${selected.reason})` : ""}.
                </p>
              )}
              <p className="mt-2 text-[11px] leading-5 text-fg-dim">
                {INERT_COPY} {SUPERSEDED_COPY} Neither means the alternative
                is bad.
              </p>
              <p className="mt-2 font-data text-[11px] tabular-nums text-fg-dim">
                {formatPairs(selected.complete_pairs, selected.requested_pairs)}
              </p>
            </div>
          </div>
          <div className="border-t border-ink-700 px-4 py-3">
            <div className={labelClass}>Pair counts</div>
            <div className="mt-2 max-w-2xl space-y-1.5">
              {response.alternatives.map((alt) => (
                <div key={alt.candidate_key} className="min-w-0">
                  <div className="flex items-baseline justify-between gap-3 font-data text-[11px] tabular-nums">
                    <span className="truncate text-fg-muted">{alt.candidate_key}</span>
                    <span className="shrink-0 text-fg">
                      {`${formatStrategyCount(alt.complete_pairs)} / ${formatStrategyCount(alt.requested_pairs)}`}
                    </span>
                  </div>
                  <ProbabilityBar
                    value={alt.requested_pairs > 0 ? alt.complete_pairs / alt.requested_pairs : 0}
                    className="mt-1 block w-full"
                  />
                </div>
              ))}
            </div>
          </div>
        </Panel>
      ) : null}

      <Panel>
        <PanelHeader
          title="Source · provenance"
          meta={response.execution_source === "cache" ? "Source cached" : "Source live engine"}
        />
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-4">
          <div className="min-w-0">
            <div className={labelClass}>Source</div>
            <div className="mt-1 font-data text-[13px] font-bold uppercase text-fg">
              {response.execution_source === "cache" ? "Cached" : "Live engine"}
            </div>
          </div>
          <div className="min-w-0">
            <div className={labelClass}>Engine</div>
            <div className="mt-1 font-data text-[13px] text-fg">Strategy 2.0</div>
          </div>
          <div className="min-w-0">
            <div className={labelClass}>Simulator</div>
            <div className="mt-1 font-data text-[13px] text-fg">MC2-E</div>
          </div>
          <div className="min-w-0">
            <div className={labelClass}>Futures</div>
            <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
              {formatStrategyCount(response.simulation_count)}
            </div>
          </div>
        </div>
        <details className="border-t border-ink-700 px-4 py-3">
          <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
            Method / provenance
          </summary>
          <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 font-data text-[12px] tabular-nums text-fg sm:grid-cols-2">
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Engine</dt>
              <dd>{response.engine_version}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Contract</dt>
              <dd>{response.execution_contract_version}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Outcome schema</dt>
              <dd>{response.outcome_schema_version}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Seed</dt>
              <dd>{response.master_seed}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">State</dt>
              <dd title={response.state_identity}>{truncateIdentity(response.state_identity)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Parameters</dt>
              <dd title={response.parameter_identity}>{truncateIdentity(response.parameter_identity)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Config</dt>
              <dd title={response.config_identity}>{truncateIdentity(response.config_identity)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Strategy identity</dt>
              <dd title={response.strategy_identity}>{truncateIdentity(response.strategy_identity)}</dd>
            </div>
            {response.cache_key ? (
              <div className="flex justify-between gap-3">
                <dt className="text-fg-dim">Cache key</dt>
                <dd title={response.cache_key}>{truncateIdentity(response.cache_key)}</dd>
              </div>
            ) : null}
            <div className="flex justify-between gap-3">
              <dt className="text-fg-dim">Complete pairs</dt>
              <dd>{String(provenance.complete_pair_count ?? "—")}</dd>
            </div>
          </dl>
          <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
            {CACHE_MISS_COPY} Raw simulation internals are never exposed.
          </p>
        </details>
      </Panel>

      <Panel>
        <PanelHeader title="Methodology · limitations" meta="Simulator-conditional" />
        <div className="grid grid-cols-1 gap-x-6 gap-y-3 px-4 py-4 lg:grid-cols-2">
          <div className="min-w-0">
            <div className={labelClass}>How to read this</div>
            <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-muted">
              <li>· Starts from the factual causal race state at time T.</li>
              <li>· Reference uses no forced intervention; alternatives change the strategy action only.</li>
              <li>· Paired simulations share stochastic structure where valid: {formatStrategyCount(response.simulation_count)} futures per action.</li>
              <li>· Outputs are simulator-conditional; historical counterfactual truth is unknowable.</li>
              <li>· MC intervals represent simulation sampling uncertainty only.</li>
            </ul>
          </div>
          <div className="min-w-0 border-t border-ink-700 pt-3 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <div className={labelClass}>Scope</div>
            <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-dim">
              <li>· Dry running only; no evolving weather or safety-car model.</li>
              <li>· Compound choice carries no pace effect.</li>
              <li>· No DNF, points, or multi-decision modelling; single driver, single decision.</li>
              <li>· 2018–2024 only; 2025 is unavailable.</li>
            </ul>
            <p className="mt-2 text-[12px] leading-5 text-fg-muted">
              Deeper modelling context lives in{" "}
              <Link href="/about" className="underline underline-offset-2 hover:text-fg">
                About
              </Link>
              .
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
