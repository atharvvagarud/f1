// Strategy comparison results (Phase-7 S7).
//
// Presentation only: the backend owns every estimate. Baseline is the
// reference (never a candidate action); candidate deltas refer back to it.
// The leader is a simulator point-estimate label, never a recommendation.
// Classification describes Monte Carlo sampling only.

"use client";

import { useState } from "react";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";
import type {
  StrategyCandidateResult,
  StrategyCompareResponse,
} from "@/lib/v2";
import {
  formatDeltaPoints,
  formatDeltaPositions,
  formatFinish,
  formatProbability,
  formatSamplingInterval,
  formatStrategyCount,
} from "@/features/strategy/lib/strategyMachine";

const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

type StatusTone = "ok" | "warn" | "danger" | "neutral";

const STATUS_TONE: Record<StatusTone, string> = {
  ok: "border-ok/60 text-ok",
  warn: "border-warn/60 text-warn",
  danger: "border-danger/60 text-danger",
  neutral: "border-ink-600 text-fg-muted",
};

function StatusChip({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <span
      role="status"
      className={`inline-block rounded-chip border px-2 py-0.5 font-ui text-[10px] font-bold uppercase tracking-[0.14em] ${STATUS_TONE[tone]}`}
    >
      {label}
    </span>
  );
}

function classificationTone(classification: string): StatusTone {
  if (classification === "IMPROVEMENT") return "ok";
  if (classification === "DEGRADATION") return "danger";
  if (classification === "INCONCLUSIVE") return "neutral";
  return "warn";
}

function executionSummary(candidate: StrategyCandidateResult): string {
  const execution = candidate.execution;
  if (!execution) return "—";
  if (candidate.action === "STAY_OUT") {
    return `suppressed ${(execution.suppressed_rate * 100).toFixed(1)}% · inert ${(execution.inert_rate * 100).toFixed(1)}%`;
  }
  if (candidate.action === "PIT_NEXT_LAP") {
    return `applied ${(execution.applied_rate * 100).toFixed(1)}% · superseded ${(execution.superseded_rate * 100).toFixed(1)}%`;
  }
  return `applied ${(execution.applied_rate * 100).toFixed(1)}%`;
}

function objectiveDeltaText(
  candidate: StrategyCandidateResult,
  metric: string,
): string {
  if (metric === "PODIUM_PROBABILITY") {
    return formatDeltaPoints(candidate.delta_podium_probability);
  }
  if (metric === "EXPECTED_FINISH") {
    return formatDeltaPositions(candidate.delta_expected_finish);
  }
  return formatDeltaPoints(candidate.delta_win_probability);
}

export function StrategyResults({
  response,
}: {
  response: StrategyCompareResponse;
}) {
  const baseline = response.baseline;
  const analysis = response.objective_analysis;
  const isFinishMetric = (analysis?.metric ?? response.metric) === "EXPECTED_FINISH";
  const [selectedKey, setSelectedKey] = useState<string | null>(
    analysis?.leader_by_point_estimate ?? null,
  );
  const selected =
    response.candidates.find((c) => c.candidate_key === selectedKey) ??
    response.candidates.find(
      (c) => c.candidate_key === analysis?.leader_by_point_estimate,
    ) ??
    response.candidates[0];

  return (
    <div className="mt-4 space-y-4">
      <Panel>
        <PanelHeader
          title="Baseline reference"
          meta={`${formatStrategyCount(response.simulation_count)} trials · seed ${response.master_seed}`}
          note="The baseline is the frozen simulator from the same factual state with ordinary stochastic pit mechanics. It is the reference every candidate delta is measured against — not a candidate intervention."
        />
        {baseline ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="min-w-0">
              <div className={labelClass}>Est. win probability</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatProbability(baseline.win_probability)}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Est. podium probability</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatProbability(baseline.podium_probability)}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Expected finish</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatFinish(baseline.expected_finish)}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Valid trials</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatStrategyCount(baseline.valid_simulations)}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Invalid trials</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {formatStrategyCount(baseline.invalid_simulations)}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Target</div>
              <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
                {response.target_driver_id}
              </div>
            </div>
          </div>
        ) : null}
      </Panel>

      {analysis ? (
        <Panel>
          <PanelHeader
            title="Point-estimate leader"
            meta={`Under ${analysis.objective}`}
            note="Leader refers to the simulator point estimate, not a recommendation."
          />
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
            <div className="min-w-0">
              <div className={labelClass}>Leader</div>
              <div className="mt-1 font-data text-[13px] font-bold text-fg tabular-nums">
                {analysis.leader_by_point_estimate ?? "—"}
              </div>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Not distinguishable from leader</div>
              <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
                {analysis.indistinguishable_from_leader.length > 0
                  ? analysis.indistinguishable_from_leader.join(", ")
                  : "—"}
              </div>
            </div>
            <div className="min-w-0 max-w-2xl">
              <div className={labelClass}>Reading</div>
              <p className="mt-1 text-[12px] leading-5 text-fg-muted">
                Candidates listed as indistinguishable cannot be separated
                from the leader under simulation sampling. A point-estimate
                lead is not evidence of a real-world advantage.
              </p>
            </div>
          </div>
        </Panel>
      ) : null}

      <Panel>
        <PanelHeader
          title="Strategy comparison"
          meta="Estimated change vs baseline · paired trials"
          note="Simulated strategy comparison. Deltas are paired differences against the shared baseline; positive means the candidate improved the estimate."
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] border-collapse text-left">
            <caption className="sr-only">
              Simulated strategy comparison for the target driver. All values
              are Monte Carlo estimates with sampling uncertainty.
            </caption>
            <thead>
              <tr className="border-b-2 border-ink-600 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                <th scope="col" className="px-4 py-2 font-medium">Candidate</th>
                <th scope="col" className="px-4 py-2 font-medium">Win</th>
                <th scope="col" className="px-4 py-2 font-medium">Δ Win</th>
                <th scope="col" className="px-4 py-2 font-medium">Podium</th>
                <th scope="col" className="px-4 py-2 font-medium">Δ Podium</th>
                <th scope="col" className="px-4 py-2 font-medium">Exp finish</th>
                <th scope="col" className="px-4 py-2 font-medium">Δ Finish</th>
                <th scope="col" className="px-4 py-2 font-medium">Objective Δ</th>
                <th scope="col" className="px-4 py-2 font-medium">95% MC interval</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="font-data text-[12px] tabular-nums">
              {response.candidates.map((candidate) => {
                const uncertainty = candidate.uncertainty;
                const isLeader =
                  candidate.candidate_key ===
                  analysis?.leader_by_point_estimate;
                return (
                  <tr
                    key={candidate.candidate_key}
                    className="border-b border-ink-700 text-fg"
                  >
                    <th
                      scope="row"
                      className="px-4 py-2 font-data text-[12px] font-semibold"
                    >
                      {candidate.candidate_key}
                      {isLeader ? (
                        <span className="ml-2">
                          <StatusChip label="Leader" tone="neutral" />
                        </span>
                      ) : null}
                      {!candidate.evaluated ? (
                        <span className="mt-0.5 block text-[11px] font-normal text-fg-dim">
                          not evaluated · {candidate.reason ?? "invalid"}
                        </span>
                      ) : null}
                    </th>
                    <td className="px-4 py-2">
                      {formatProbability(candidate.win_probability)}
                    </td>
                    <td className="px-4 py-2">
                      {formatDeltaPoints(candidate.delta_win_probability)}
                    </td>
                    <td className="px-4 py-2">
                      {formatProbability(candidate.podium_probability)}
                    </td>
                    <td className="px-4 py-2">
                      {formatDeltaPoints(candidate.delta_podium_probability)}
                    </td>
                    <td className="px-4 py-2">
                      {formatFinish(candidate.expected_finish)}
                    </td>
                    <td className="px-4 py-2">
                      {formatDeltaPositions(candidate.delta_expected_finish)}
                    </td>
                    <td className="px-4 py-2">
                      {candidate.evaluated
                        ? objectiveDeltaText(candidate, response.metric)
                        : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {uncertainty
                        ? formatSamplingInterval(
                            uncertainty.ci_low,
                            uncertainty.ci_high,
                            isFinishMetric,
                          )
                        : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {uncertainty ? (
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          <StatusChip
                            label={uncertainty.classification}
                            tone={classificationTone(
                              uncertainty.classification,
                            )}
                          />
                          <span className="text-[11px] text-fg-dim">
                            {executionSummary(candidate)}
                          </span>
                        </span>
                      ) : (
                        <span className="text-fg-dim">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="border-t border-ink-700 px-4 py-3">
          <SemanticsNote>
            Win/podium deltas are percentage points; expected-finish deltas
            are positions (positive = estimated improvement). Classification
            is under simulation sampling only.
          </SemanticsNote>
        </div>
      </Panel>

      {selected ? (
        <Panel>
          <PanelHeader
            title="Selected candidate detail"
            meta={selected.candidate_key}
            note="Counterfactual simulation: the alternative future did not occur. These are simulator-conditional estimates, not observed outcomes."
          />
          <div className="border-b border-ink-700 px-4 py-3">
            <label htmlFor="strategy-candidate-detail" className={labelClass}>
              Candidate
            </label>
            <select
              id="strategy-candidate-detail"
              value={selected.candidate_key}
              onChange={(event) => setSelectedKey(event.target.value)}
              className="mt-1.5 h-9 w-full max-w-md border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg focus-visible:outline-2 focus-visible:outline-focus"
            >
              {response.candidates.map((candidate) => (
                <option
                  key={candidate.candidate_key}
                  value={candidate.candidate_key}
                >
                  {candidate.candidate_key}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-3">
            <div className="min-w-0">
              <div className={labelClass}>Finish-position distribution</div>
              {selected.finish_position_distribution.length > 0 ? (
                <table className="mt-2 w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-ink-700 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                      <th scope="col" className="py-1 pr-3 font-medium">Pos</th>
                      <th scope="col" className="py-1 font-medium">Frequency</th>
                    </tr>
                  </thead>
                  <tbody className="font-data text-[12px] tabular-nums text-fg">
                    {selected.finish_position_distribution.map((bucket) => (
                      <tr
                        key={String(bucket.position)}
                        className="border-b border-ink-700"
                      >
                        <th scope="row" className="py-1 pr-3 font-normal">
                          {bucket.position ?? "—"}
                        </th>
                        <td className="py-1">
                          {formatProbability(bucket.frequency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="mt-2 text-[12px] text-fg-dim">
                  No distribution: candidate was not evaluated
                  {selected.reason ? ` (${selected.reason})` : ""}.
                </p>
              )}
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Execution and activation</div>
              {selected.execution ? (
                <dl className="mt-2 space-y-1 font-data text-[12px] tabular-nums text-fg">
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Applied</dt>
                    <dd>{(selected.execution.applied_rate * 100).toFixed(1)}%</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Suppressed</dt>
                    <dd>{(selected.execution.suppressed_rate * 100).toFixed(1)}%</dd>
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
                    <dt className="text-fg-dim">Race-end cancelled</dt>
                    <dd>{(selected.execution.race_end_cancelled_rate * 100).toFixed(1)}%</dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-2 text-[12px] text-fg-dim">—</p>
              )}
              <p className="mt-2 text-[11px] leading-5 text-fg-dim">
                A frequently inert or superseded intervention with a near-zero
                delta is not evidence of equivalence.
              </p>
            </div>
            <div className="min-w-0">
              <div className={labelClass}>Sampling uncertainty</div>
              {selected.uncertainty ? (
                <dl className="mt-2 space-y-1 font-data text-[12px] tabular-nums text-fg">
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Objective Δ</dt>
                    <dd>
                      {objectiveDeltaText(selected, response.metric)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Paired SE</dt>
                    <dd>
                      {selected.uncertainty.paired_se !== null
                        ? (isFinishMetric
                            ? selected.uncertainty.paired_se.toFixed(3)
                            : `${(selected.uncertainty.paired_se * 100).toFixed(2)} pp`)
                        : "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">95% MC interval</dt>
                    <dd className="text-right">
                      {formatSamplingInterval(
                        selected.uncertainty.ci_low,
                        selected.uncertainty.ci_high,
                        isFinishMetric,
                      )}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-fg-dim">Classification</dt>
                    <dd>
                      <StatusChip
                        label={selected.uncertainty.classification}
                        tone={classificationTone(
                          selected.uncertainty.classification,
                        )}
                      />
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-dim">Valid pairs</dt>
                    <dd>{formatStrategyCount(selected.uncertainty.valid_pairs)}</dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-2 text-[12px] text-fg-dim">—</p>
              )}
            </div>
          </div>
          <div className="border-t border-ink-700 px-4 py-3">
            <div className={labelClass}>Limitations</div>
            <ul className="mt-2 max-w-4xl space-y-1 text-[12px] leading-5 text-fg-dim">
              {response.limitations.slice(0, 6).map((limitation) => (
                <li key={limitation.slice(0, 48)}>· {limitation}</li>
              ))}
            </ul>
            <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
              {response.counterfactual_semantics}
            </p>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
