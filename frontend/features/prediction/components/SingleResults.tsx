"use client";

import { Activity, Flag, Gauge, LineChart, Trophy } from "lucide-react";
import ProbabilityChart from "@/components/prediction/ProbabilityChart";
import type { MainTab, ModelId, SingleModelResult } from "@/lib/predictionTypes";
import { formatDriverName, formatPercent, titleCaseModelName } from "@/lib/predictionHelpers";
import { buildChartRows } from "../lib/predictionTransforms";
import { ChartInsightCard, OverviewCard } from "./ResultCards";
import { CompactDriverRow, DriverCard } from "./DriverCards";

type SingleResultsProps = {
  singleResult: SingleModelResult;
  model: ModelId;
  event: string;
  year: number;
  activeTab: MainTab;
};

export default function SingleResults({ singleResult, model, event, year, activeTab }: SingleResultsProps) {
  const chartRows = buildChartRows("single", model, null, singleResult);
  return (
            <>
              {activeTab === "overview" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-4xl font-bold tracking-tight text-white">
                        Race Prediction Overview
                      </h2>
                      <p className="font-body mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        A compact summary of the selected model output, race
                        context, checkpoint used, and comparison against the
                        actual winner.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {event} ({year})
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
                    <OverviewCard
                      icon={<Trophy className="h-5 w-5 text-emerald-300" />}
                      label="Final Winner Prediction"
                      value={formatDriverName(
                        singleResult.latest.predicted_winner,
                      )}
                      subvalue="Selected model output"
                    />
                    <OverviewCard
                      icon={<Flag className="h-5 w-5 text-red-300" />}
                      label="Actual Winner"
                      value={formatDriverName(
                        singleResult.latest.actual_winner,
                      )}
                      subvalue="Official race result"
                    />
                    <OverviewCard
                      icon={<Activity className="h-5 w-5 text-cyan-300" />}
                      label="Latest Checkpoint"
                      value={`Lap ${singleResult.latest.lap}`}
                      subvalue="Final checkpoint included"
                    />
                    <OverviewCard
                      icon={<Gauge className="h-5 w-5 text-amber-300" />}
                      label="Prediction Model"
                      value={titleCaseModelName(model)}
                      subvalue="Current active model"
                    />
                  </div>

                  <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
                    <OverviewCard
                      icon={<Gauge className="h-5 w-5 text-violet-300" />}
                      label="Confidence"
                      value={formatPercent(
                        singleResult.latest.predicted_win_probability,
                      )}
                      subvalue="Final confidence score"
                    />
                    <OverviewCard
                      icon={<Trophy className="h-5 w-5 text-sky-300" />}
                      label="Prediction Status"
                      value={
                        singleResult.latest.actual_winner ===
                        singleResult.latest.predicted_winner
                          ? "Matched"
                          : "Not matched"
                      }
                      subvalue="Compared against actual result"
                    />
                    <OverviewCard
                      icon={<LineChart className="h-5 w-5 text-fuchsia-300" />}
                      label="Prediction Summary"
                      value="Single model"
                      subvalue={`Inference via ${titleCaseModelName(model)}`}
                    />
                  </div>
                </div>
              )}

              {activeTab === "table" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <h2 className="text-4xl font-bold tracking-tight text-white">
                    Single Model Prediction Summary
                  </h2>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
                    Checkpoint-by-checkpoint output for the selected model,
                    including predicted winner, win chance, and actual finish
                    context.
                  </p>
                  <div className="mt-5 overflow-x-auto rounded-[24px] border border-white/10 bg-slate-950/20">
                    <table className="w-full min-w-[760px] text-left text-[15px] text-slate-200">
                      <thead className="bg-slate-800/90 text-slate-200">
                        <tr>
                          <th className="px-4 py-3">Checkpoint</th>
                          <th className="px-4 py-3">Predicted Winner</th>
                          <th className="px-4 py-3">Win Chance</th>
                          <th className="px-4 py-3">Actual Winner</th>
                          <th className="px-4 py-3">Actual Finish</th>
                        </tr>
                      </thead>
                      <tbody>
                        {singleResult.summary.map((row, idx) => (
                          <tr
                            key={idx}
                            className="border-t border-white/10 bg-slate-950/10 transition hover:bg-white/[0.04]"
                          >
                            <td className="px-4 py-3">Lap {row.lap}</td>
                            <td className="px-4 py-3">
                              {formatDriverName(row.predicted_winner)}
                            </td>
                            <td className="px-4 py-3">
                              {formatPercent(row.win_probability)}
                            </td>
                            <td className="px-4 py-3">
                              {formatDriverName(row.actual_winner)}
                            </td>
                            <td className="px-4 py-3">
                              {row.actual_rank ? `P${row.actual_rank}` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeTab === "chart" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="font-heading text-4xl font-bold tracking-tight text-white">
                        Winner Probability by Lap
                      </h2>
                      <p className="font-body mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        Checkpoint-by-checkpoint win probability trend for the
                        selected prediction model.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {titleCaseModelName(model)}
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4 md:grid-cols-3">
                    <ChartInsightCard
                      label="Highest confidence"
                      value={`${formatPercent(
                        Math.max(
                          ...Object.values(chartRows)
                            .flat()
                            .map((p) => p.value),
                        ),
                      )}`}
                      subvalue="Peak confidence shown on the chart"
                    />
                    <ChartInsightCard
                      label="Race laps shown"
                      value={`${Object.values(chartRows)[0]?.length ?? 0}`}
                      subvalue="Displayed checkpoints on the timeline"
                    />
                    <ChartInsightCard
                      label="Model"
                      value={titleCaseModelName(model)}
                      subvalue="Active prediction model"
                    />
                  </div>

                  <div className="mt-6">
                    <ProbabilityChart groupedData={chartRows} />
                  </div>
                </div>
              )}

              {activeTab === "drivers" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="font-heading text-4xl font-bold tracking-tight text-white">
                        Top Win Probability Drivers
                      </h2>
                      <p className="font-body mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        Final checkpoint ranking for the selected model, with
                        the leading driver highlighted and the remaining
                        contenders shown in compact form.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {titleCaseModelName(model)}
                    </div>
                  </div>

                  <div className="mt-6">
                    <div className="rounded-[26px] border border-white/10 bg-gradient-to-br from-slate-950/75 via-slate-950/55 to-slate-900/40 p-5 shadow-xl">
                      <div className="mb-5 flex items-start justify-between gap-3">
                        <div className="min-w-0 pr-3">
                          <h3 className="font-heading text-[22px] font-semibold leading-tight text-white">
                            {titleCaseModelName(model)}
                          </h3>
                          <p className="mt-1 text-sm text-slate-300">
                            Final top 5 at displayed checkpoint
                          </p>
                        </div>

                        <span className="shrink-0 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                          Lap {singleResult.latest.lap}
                        </span>
                      </div>

                      <div className="space-y-4">
                        {singleResult.latest.top5[0] && (
                          <DriverCard
                            key={`${model}-${singleResult.latest.top5[0].driver}`}
                            driver={singleResult.latest.top5[0]}
                            rank={1}
                            accent="from-white to-slate-300"
                          />
                        )}

                        {singleResult.latest.top5.length > 1 && (
                          <div className="rounded-[22px] border border-white/10 bg-slate-950/35 p-3">
                            <div className="mb-3 px-2 text-[11px] uppercase tracking-[0.14em] text-slate-500">
                              Remaining contenders
                            </div>

                            <div className="space-y-2">
                              {singleResult.latest.top5
                                .slice(1)
                                .map((driver, idx) => (
                                  <CompactDriverRow
                                    key={`${model}-${driver.driver}`}
                                    driver={driver}
                                    rank={idx + 2}
                                    accent="from-white to-slate-300"
                                  />
                                ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
  );
}

