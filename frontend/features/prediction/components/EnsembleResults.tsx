"use client";

import { motion } from "motion/react";
import { Activity, Flag, Gauge, LineChart, Trophy, Users } from "lucide-react";
import ProbabilityChart from "@/components/prediction/ProbabilityChart";
import type { EnsembleResult, MainTab } from "@/lib/predictionTypes";
import { formatDriverName, formatPercent, titleCaseModelName } from "@/lib/predictionHelpers";
import { buildChartRows, groupEnsembleSummaryByLap } from "../lib/predictionTransforms";
import { ChartInsightCard, OverviewCard } from "./ResultCards";
import { CompactDriverRow, DriverCard } from "./DriverCards";

type EnsembleResultsProps = {
  ensembleResult: EnsembleResult;
  event: string;
  year: number;
  activeTab: MainTab;
};

export default function EnsembleResults({ ensembleResult, event, year, activeTab }: EnsembleResultsProps) {
  const chartRows = buildChartRows("ensemble", "xgboost", ensembleResult, null);
  const groupedEnsembleSummary = groupEnsembleSummaryByLap(ensembleResult.summary);
  return (
            <>
              {activeTab === "overview" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="font-heading text-4xl font-bold tracking-tight text-white sm:text-[2.6rem]">
                        Race Prediction Overview
                      </h2>
                      <p className="font-body mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        A compact summary of the final ensemble decision, race
                        context, agreement signal, and actual result.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {event} ({year})
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-4">
                    <OverviewCard
                      icon={<Trophy className="h-5 w-5 text-white" />}
                      label="Final Winner Prediction"
                      value={formatDriverName(ensembleResult.final_winner)}
                      subvalue="Ensemble output"
                    />
                    <OverviewCard
                      icon={<Flag className="h-5 w-5 text-white" />}
                      label="Actual Winner"
                      value={formatDriverName(ensembleResult.actual_winner)}
                      subvalue="Official race result"
                    />
                    <OverviewCard
                      icon={<Activity className="h-5 w-5 text-white" />}
                      label="Latest Checkpoint Used"
                      value={`Lap ${ensembleResult.latest_lap}`}
                      subvalue="Final checkpoint included"
                    />
                    <OverviewCard
                      icon={<Users className="h-5 w-5 text-white" />}
                      label="Model Agreement"
                      value={`${ensembleResult.agreement_count} / 3`}
                      subvalue="Models aligned"
                    />
                  </div>

                  <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <OverviewCard
                      icon={<Gauge className="h-5 w-5 text-white" />}
                      label="Confidence"
                      value={formatPercent(ensembleResult.confidence_value)}
                      subvalue="Final confidence score"
                    />
                    <OverviewCard
                      icon={<Trophy className="h-5 w-5 text-white" />}
                      label="Prediction Status"
                      value={
                        ensembleResult.actual_winner &&
                        ensembleResult.final_winner ===
                          ensembleResult.actual_winner
                          ? "Matched"
                          : "Not matched"
                      }
                      subvalue="Compared against actual result"
                    />
                    <OverviewCard
                      icon={<LineChart className="h-5 w-5 text-white" />}
                      label="Decision Summary"
                      value="Majority vote"
                      subvalue={ensembleResult.decision_reason}
                    />
                  </div>
                </div>
              )}

              {activeTab === "table" && (
                <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/75 to-slate-800/60 p-6 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="font-heading text-4xl font-extrabold tracking-[-0.03em] text-white sm:text-[2.6rem]">
                        Prediction Timeline
                      </h2>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        A lap-by-lap view of who each model predicted to win,
                        how confident it was, and how that compared with the
                        real race result.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {event} ({year})
                    </div>
                  </div>

                  <div className="mt-6 space-y-5">
                    {Object.entries(groupedEnsembleSummary)
                      .sort(([a], [b]) => Number(a) - Number(b))
                      .map(([lap, rows]) => (
                        <div
                          key={lap}
                          className="overflow-x-auto rounded-[24px] border border-white/10 bg-slate-950/20"
                        >
                          <div className="border-b border-white/10 bg-white/[0.03] px-5 py-3">
                            <div className="font-heading text-lg font-bold text-white">
                              Lap {lap}
                            </div>
                            <div className="mt-1 text-sm text-slate-400">
                              Model predictions at this stage of the race
                            </div>
                          </div>

                          <table className="w-full min-w-[860px] text-left text-[15px] text-slate-200">
                            <thead className="bg-slate-800/90 text-slate-200">
                              <tr>
                                <th className="font-heading px-4 py-3">
                                  Model
                                </th>
                                <th className="font-heading px-4 py-3">
                                  Predicted Winner
                                </th>
                                <th className="font-heading px-4 py-3">
                                  Confidence
                                </th>
                                <th className="font-heading px-4 py-3">
                                  Actual Winner
                                </th>
                                <th className="font-heading px-4 py-3">
                                  Actual Position
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((row, idx) => (
                                <tr
                                  key={`${row.lap}-${row.model}-${idx}`}
                                  className={`border-t border-white/10 transition hover:bg-white/[0.04] ${
                                    idx % 2 === 0
                                      ? "bg-slate-950/10"
                                      : "bg-slate-950/20"
                                  }`}
                                >
                                  <td className="px-4 py-3">
                                    {titleCaseModelName(row.model)}
                                  </td>
                                  <td className="px-4 py-3">
                                    {formatDriverName(row.predicted_winner)}
                                  </td>
                                  <td className="px-4 py-3 font-semibold text-slate-200">
                                    {formatPercent(row.win_probability)}
                                  </td>
                                  <td className="px-4 py-3">
                                    {formatDriverName(row.actual_winner)}
                                  </td>
                                  <td className="px-4 py-3">
                                    {row.actual_rank
                                      ? `P${row.actual_rank}`
                                      : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}
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
                        Checkpoint-by-checkpoint win probability trend across
                        the displayed race laps.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      {event} ({year})
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
                      subvalue="Peak model confidence shown on the chart"
                    />
                    <ChartInsightCard
                      label="Race laps shown"
                      value={`${Object.values(chartRows)[0]?.length ?? 0}`}
                      subvalue="Displayed checkpoints on the timeline"
                    />
                    <ChartInsightCard
                      label="Models compared"
                      value={`${Object.keys(chartRows).length}`}
                      subvalue="Prediction models included in this view"
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
                        Final checkpoint ranking by model, with the leading
                        prediction featured and the remaining contenders shown
                        as compact comparisons.
                      </p>
                    </div>

                    <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
                      Lap {ensembleResult.latest_lap}
                    </div>
                  </div>

                  <div className="mt-6 grid gap-5 xl:grid-cols-3">
                    {Object.entries(ensembleResult.latest_top5).map(
                      ([modelName, drivers], idx) => (
                        <motion.div
                          key={modelName}
                          initial={{ opacity: 0, y: 18 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.35, delay: idx * 0.06 }}
                          className="rounded-[26px] border border-white/10 bg-gradient-to-br from-slate-950/75 via-slate-950/55 to-slate-900/40 p-5 shadow-xl"
                        >
                          <div className="mb-5 flex items-start justify-between gap-3">
                            <div className="min-w-0 pr-3">
                              <h3 className="font-heading text-[22px] font-semibold leading-tight text-white">
                                {titleCaseModelName(modelName)}
                              </h3>
                              <p className="mt-1 text-sm text-slate-300">
                                Final top 5 at displayed checkpoint
                              </p>
                            </div>

                            <span className="shrink-0 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                              Lap {ensembleResult.latest_lap}
                            </span>
                          </div>

                          <div className="space-y-4">
                            {drivers[0] && (
                              <DriverCard
                                key={`${modelName}-${drivers[0].driver}`}
                                driver={drivers[0]}
                                rank={1}
                                accent="from-white to-slate-300"
                              />
                            )}

                            {drivers.length > 1 && (
                              <div className="rounded-[22px] border border-white/10 bg-slate-950/35 p-3">
                                <div className="mb-3 px-2 text-[11px] uppercase tracking-[0.14em] text-slate-500">
                                  Remaining contenders
                                </div>

                                <div className="space-y-2">
                                  {drivers.slice(1).map((driver, driverIdx) => (
                                    <CompactDriverRow
                                      key={`${modelName}-${driver.driver}`}
                                      driver={driver}
                                      rank={driverIdx + 2}
                                      accent="from-white to-slate-300"  
                                    />
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </motion.div>
                      ),
                    )}
                  </div>
                </div>
              )}
            </>
  );
}

