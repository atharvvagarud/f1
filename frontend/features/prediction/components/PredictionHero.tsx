"use client";

import { motion } from "motion/react";
import { Activity, Gauge, Trophy, Users } from "lucide-react";
import type { EnsembleResult, ModelId, PredictionMode, SingleModelResult } from "@/lib/predictionTypes";
import { formatDriverName, formatPercent, getConfidenceTone, titleCaseModelName } from "@/lib/predictionHelpers";
import { ConfidenceBar } from "./ResultCards";

type PredictionHeroProps = {
  mode: PredictionMode;
  model: ModelId;
  event: string;
  year: number;
  ensembleResult: EnsembleResult | null;
  singleResult: SingleModelResult | null;
};

export default function PredictionHero({ mode, model, event, year, ensembleResult, singleResult }: PredictionHeroProps) {
  return (
            <motion.section
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="col-span-12 overflow-hidden rounded-[30px] border border-white/10 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 shadow-[0_30px_80px_rgba(0,0,0,0.35)] lg:col-span-8"
            >
              {mode === "ensemble" && ensembleResult ? (
                (() => {
                  const tone = getConfidenceTone(
                    ensembleResult.confidence_value,
                  );
                  const matched =
                    ensembleResult.actual_winner &&
                    ensembleResult.final_winner ===
                      ensembleResult.actual_winner;

                  return (
                    <div className="relative h-full p-7 sm:p-8">
                      <div
                        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/[0.04] via-white/[0.02] to-transparent"
                      />
                      <div className="relative">
                        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                          <Trophy className="h-3.5 w-3.5 text-white" />
                          Ensemble prediction
                        </div>

                        <div className="mt-5 flex flex-wrap items-start justify-between gap-5">
                          <div>
                            <h2 className="font-heading text-6xl font-extrabold tracking-[-0.04em] text-white sm:text-6xl xl:text-[5rem]">
                              {formatDriverName(ensembleResult.final_winner)}
                            </h2>
                            <p className="mt-3 text-lg text-slate-300">
                              {event} ({year})
                            </p>
                          </div>

                          <div
                            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200"
                          >
                            {ensembleResult.confidence_label}:{" "}
                            {formatPercent(ensembleResult.confidence_value)}
                          </div>
                        </div>

                        <div className="mt-8 max-w-2xl">
                          <ConfidenceBar
                            value={ensembleResult.confidence_value}
                            barClassName={tone.bar}
                          />
                        </div>

                        <div className="mt-6 flex flex-wrap gap-3">
                          <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                            <Activity className="h-4 w-4 text-white/70" />
                            Latest checkpoint:
                            <span className="font-medium text-white">
                              Lap {ensembleResult.latest_lap}
                            </span>
                          </div>

                          <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                            <Users className="h-4 w-4 text-white" />
                            Agreement:
                            <span className="font-medium text-white">
                              {ensembleResult.agreement_count} / 3
                            </span>
                          </div>

                          <div
                            className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm ${
                              matched
                                ? "border-white/10 bg-white/5 text-slate-200"
                                : "border-white/10 bg-white/5 text-slate-300"
                            }`}
                          >
                            {matched
                              ? "Matched actual result"
                              : "Did not match actual result"}
                          </div>
                        </div>

                        <div className="mt-6 rounded-[24px] border border-white/10 bg-white/5 px-5 py-4 text-sm leading-6 text-slate-200">
                          <span className="font-semibold">Decision:</span>{" "}
                          {ensembleResult.decision_reason}
                        </div>
                      </div>
                    </div>
                  );
                })()
              ) : mode === "single" && singleResult ? (
                (() => {
                  const tone = getConfidenceTone(
                    singleResult.latest.predicted_win_probability,
                  );
                  const matched =
                    singleResult.latest.actual_winner ===
                    singleResult.latest.predicted_winner;

                  return (
                    <div className="relative h-full p-7 sm:p-8">
                      <div
                        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/[0.04] via-white/[0.02] to-transparent"
                      />
                      <div className="relative">
                        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                          <Gauge className="h-3.5 w-3.5 text-white" />
                          Single model prediction
                        </div>

                        <div className="mt-5 flex flex-wrap items-start justify-between gap-5">
                          <div>
                            <h2 className="font-heading text-5xl font-extrabold tracking-[-0.04em] text-white sm:text-6xl xl:text-[5rem]">
                              {formatDriverName(
                                singleResult.latest.predicted_winner,
                              )}
                            </h2>
                            <p className="mt-3 text-lg text-slate-300">
                              {event} ({year})
                            </p>
                          </div>

                          <div
                            className={`rounded-full border px-4 py-2 text-sm font-medium ${tone.pill}`}
                          >
                            Model confidence:{" "}
                            {formatPercent(
                              singleResult.latest.predicted_win_probability,
                            )}
                          </div>
                        </div>

                        <div className="mt-8 max-w-2xl">
                          <ConfidenceBar
                            value={
                              singleResult.latest.predicted_win_probability
                            }
                            barClassName={tone.bar}
                          />
                        </div>

                        <div className="mt-6 flex flex-wrap gap-3">
                          <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                            <Activity className="h-4 w-4 text-white" />
                            Latest checkpoint:
                            <span className="font-medium text-white">
                              Lap {singleResult.latest.lap}
                            </span>
                          </div>

                          <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                            <Gauge className="h-4 w-4 text-violet-400" />
                            Prediction model:
                            <span className="font-medium text-white">
                              {titleCaseModelName(model)}
                            </span>
                          </div>

                          <div
                            className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm ${
                              matched
                                ? "border-white/10 bg-white/5 text-slate-200"
                                : "border-white/10 bg-white/5 text-slate-300"
                            }`}
                          >
                            {matched
                              ? "Matched actual result"
                              : "Did not match actual result"}
                          </div>
                        </div>

                        <div className="mt-6 rounded-[24px] border border-white/10 bg-white/5 px-5 py-4 text-sm leading-6 text-slate-200">
                          <span className="font-semibold">Prediction:</span>{" "}
                          Single model inference using{" "}
                          {titleCaseModelName(model)} at the displayed
                          checkpoint.
                        </div>
                      </div>
                    </div>
                  );
                })()
              ) : (
                <div className="relative h-full p-7 sm:p-8">
                  <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/5 via-white/[0.03] to-transparent" />

                  <div className="relative">
                    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
                      <Gauge className="h-3.5 w-3.5 text-red-400" />
                      Prediction preview
                    </div>

                    <div className="mt-5">
                      <h2 className="text-4xl font-bold tracking-tight text-white sm:text-5xl">
                        Select a race to generate a prediction
                      </h2>
                      <p className="mt-3 max-w-2xl text-slate-300">
                        Choose a season, Grand Prix, and prediction mode to view
                        the projected race winner, confidence trend, and top
                        driver probabilities.
                      </p>
                    </div>

                    <div className="mt-8 max-w-2xl">
                      <ConfidenceBar
                        value={0.0}
                        barClassName="from-slate-600 via-slate-500 to-slate-400"
                      />
                    </div>

                    <div className="mt-6 flex flex-wrap gap-3">
                      <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                        <Activity className="h-4 w-4 text-cyan-400" />
                        Race:
                        <span className="font-medium text-white">
                          {event ? `${event} (${year})` : "Not selected"}
                        </span>
                      </div>

                      <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                        <Gauge className="h-4 w-4 text-violet-400" />
                        Mode:
                        <span className="font-medium text-white">
                          {mode === "ensemble" ? "Ensemble" : "Single model"}
                        </span>
                      </div>
                    </div>

                    <div className="mt-6 rounded-[24px] border border-white/10 bg-slate-800/60 px-5 py-4 text-sm leading-6 text-slate-200">
                      Run a prediction to unlock the race overview, lap-by-lap
                      probability chart, top drivers, and checkpoint table.
                    </div>
                  </div>
                </div>
              )}
            </motion.section>
  );
}

