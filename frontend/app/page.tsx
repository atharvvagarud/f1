"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Flag,
  Trophy,
  Gauge,
  Users,
  Activity,
  LineChart,
  Table2,
  LayoutGrid,
} from "lucide-react";
import { getRaces, predictEnsemble, predictSingleModel } from "@/lib/api";

import type {
  Race,
  EnsembleSummaryRow,
  DriverRow,
  EnsembleResult,
  SingleSummaryRow,
  SingleLatest,
  SingleModelResult,
  MainTab,
} from "@/lib/predictionTypes";

import {
  formatPercent,
  formatGap,
  formatWhole,
  getConfidenceTone,
  titleCaseModelName,
  formatDriverName,
} from "@/lib/predictionHelpers";

import PredictionTabs from "@/components/prediction/PredictionTabs";
import ProbabilityChart from "@/components/prediction/ProbabilityChart";
import ControlsPanel from "@/components/prediction/ControlsPanel";

export default function HomePage() {
  const [races, setRaces] = useState<Race[]>([]);
  const [year, setYear] = useState<number>(2023);
  const [event, setEvent] = useState<string>("");
  const [mode, setMode] = useState<"ensemble" | "single">("ensemble");
  const [model, setModel] = useState<"logreg" | "hgb" | "xgboost">("xgboost");
  const [loading, setLoading] = useState(false);
  const [ensembleResult, setEnsembleResult] = useState<EnsembleResult | null>(
    null,
  );
  const [singleResult, setSingleResult] = useState<SingleModelResult | null>(
    null,
  );
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<MainTab>("overview");

  useEffect(() => {
    async function loadRaces() {
      try {
        const data = await getRaces();
        const loadedRaces: Race[] = data.races;
        setRaces(loadedRaces);

        const years = [...new Set(loadedRaces.map((r) => r.year))].sort();
        const latestYear = years[years.length - 1];
        setYear(latestYear);

        const eventsForLatest = loadedRaces
          .filter((r) => r.year === latestYear)
          .map((r) => r.event_name);

        if (eventsForLatest.length > 0) {
          setEvent(eventsForLatest[0]);
        }
      } catch {
        setError("Failed to load races from API.");
      }
    }

    loadRaces();
  }, []);

  const years = useMemo(() => {
    return [...new Set(races.map((r) => r.year))].sort((a, b) => a - b);
  }, [races]);

  const events = useMemo(() => {
    return races.filter((r) => r.year === year).map((r) => r.event_name);
  }, [races, year]);

  useEffect(() => {
    if (events.length > 0 && !events.includes(event)) {
      setEvent(events[0]);
    }
  }, [events, event]);

  async function handlePredict() {
    if (!event) return;

    setLoading(true);
    setError("");
    setEnsembleResult(null);
    setSingleResult(null);

    try {
      if (mode === "ensemble") {
        const data = await predictEnsemble(year, event);
        setEnsembleResult(data);
      } else {
        const data = await predictSingleModel(year, event, model);
        setSingleResult(data);
      }
      setActiveTab("overview");
    } catch {
      setError("Prediction request failed. Check the API server.");
    } finally {
      setLoading(false);
    }
  }

  const isCorrect =
    ensembleResult?.actual_winner &&
    ensembleResult.final_winner === ensembleResult.actual_winner;

  const chartRows = useMemo(() => {
    if (mode === "ensemble" && ensembleResult) {
      const grouped: Record<string, { lap: number; value: number }[]> = {};
      for (const row of ensembleResult.summary) {
        if (!grouped[row.model]) grouped[row.model] = [];
        grouped[row.model].push({ lap: row.lap, value: row.win_probability });
      }
      Object.keys(grouped).forEach((k) =>
        grouped[k].sort((a, b) => a.lap - b.lap),
      );
      return grouped;
    }

    if (mode === "single" && singleResult) {
      return {
        [model.toUpperCase()]: singleResult.summary.map((row) => ({
          lap: row.lap,
          value: row.win_probability,
        })),
      };
    }

    return {};
  }, [ensembleResult, singleResult, mode, model]);

  const groupedEnsembleSummary =
    ensembleResult?.summary.reduce<
      Record<number, typeof ensembleResult.summary>
    >((acc, row) => {
      if (!acc[row.lap]) acc[row.lap] = [];
      acc[row.lap].push(row);
      return acc;
    }, {}) ?? {};

  const hasPrediction =
    (mode === "ensemble" && ensembleResult !== null) ||
    (mode === "single" && singleResult !== null);

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div
        className={`mx-auto max-w-7xl px-6 ${
          hasPrediction
            ? "py-10"
            : "min-h-screen flex items-center justify-center"
        }`}
      >
        {error && (
          <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-slate-200">
            {error}
          </div>
        )}
        <div className="w-full">
          <div className="mx-auto grid max-w-6xl grid-cols-12 gap-6">
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

            <ControlsPanel
              year={year}
              years={years}
              setYear={setYear}
              event={event}
              events={events}
              setEvent={setEvent}
              mode={mode}
              setMode={setMode}
              model={model}
              setModel={setModel}
              loading={loading}
              handlePredict={handlePredict}
            />
          </div>
        </div>

        {hasPrediction && (
          <div className="mx-auto mt-6 flex max-w-6xl justify-center">
            <PredictionTabs activeTab={activeTab} setActiveTab={setActiveTab} />
          </div>
        )}

        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="mt-6 space-y-6"
        >
          {mode === "ensemble" && ensembleResult && (
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
          )}

          {mode === "single" && singleResult && (
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
          )}
        </motion.section>
      </div>
    </main>
  );
}

function ConfidenceBar({
  value,
  barClassName,
}: {
  value: number;
  barClassName: string;
}) {
  const safe = Math.max(0, Math.min(1, value));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-slate-400">Confidence strength</span>
        <span className="font-medium text-slate-200">
          {formatPercent(safe)}
        </span>
      </div>

      <div className="relative h-3 overflow-hidden rounded-full bg-slate-800 ring-1 ring-white/10">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(safe * 100, 4)}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="relative h-full rounded-full bg-white"
        >
          <div className="absolute inset-0 bg-[linear-gradient(110deg,transparent,rgba(255,255,255,0.25),transparent)] opacity-80" />
        </motion.div>
      </div>
    </div>
  );
}

function OverviewCard({
  icon,
  label,
  value,
  subvalue,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subvalue?: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="group rounded-[26px] border border-white/10 bg-gradient-to-br from-slate-950/75 via-slate-950/55 to-slate-900/35 p-5 shadow-xl transition-all hover:border-white/15"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-white/5 p-2 ring-1 ring-white/10 transition group-hover:bg-white/10">
          {icon}
        </div>
        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
          {label}
        </div>
      </div>

      <div className="font-heading mt-4 text-2xl font-semibold tracking-tight text-white xl:text-[1.7rem]">
        {value}
      </div>

      {subvalue && (
        <div className="mt-2 text-sm leading-6 text-slate-400">{subvalue}</div>
      )}
    </motion.div>
  );
}

function ChartInsightCard({
  label,
  value,
  subvalue,
}: {
  label: string;
  value: string;
  subvalue: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="rounded-[22px] border border-white/10 bg-gradient-to-br from-slate-950/70 via-slate-950/50 to-slate-900/30 px-5 py-4 shadow-xl transition-all hover:border-white/15"
    >
      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
        {label}
      </div>
      <div className="font-heading mt-3 text-2xl font-bold tracking-tight text-white">
        {value}
      </div>
      <div className="mt-2 text-sm leading-6 text-slate-400">{subvalue}</div>
    </motion.div>
  );
}

function DriverCard({
  driver,
  rank,
  accent = "from-white to-slate-300",
}: {
  driver: DriverRow;
  rank: number;
  accent?: string;
}) {
  const safeProb = Math.max(0, Math.min(1, driver.win_probability));
  const probWidth = Math.max(safeProb * 100, 2);
  const isLeader = rank === 1;

  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className={`rounded-2xl border px-4 py-4 transition-all hover:border-white/15 ${
        isLeader
          ? "border-white/15 bg-slate-900/80 shadow-lg shadow-black/10"
          : "border-white/8 bg-slate-900/70"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div
              className={`inline-flex h-7 min-w-7 items-center justify-center rounded-lg px-2 text-[11px] font-semibold ${
                isLeader
                  ? "bg-white/10 text-white ring-1 ring-white/15"
                  : "bg-white/5 text-slate-300 ring-1 ring-white/10"
              }`}
            >
              P{rank}
            </div>

            <h4 className="font-heading truncate text-[17px] font-semibold tracking-tight text-white">
              {formatDriverName(driver.driver)}
            </h4>
          </div>

          <div className="mt-1 text-sm text-slate-400">
            Driver #{driver.driver_number}
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-heading text-2xl font-bold tracking-tight text-white">
            {formatPercent(safeProb)}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Win chance
          </div>
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="text-slate-400">Win probability</span>
          <span className="font-medium text-slate-300">
            {formatPercent(safeProb)}
          </span>
        </div>

        <div className="h-2.5 overflow-hidden rounded-full bg-slate-800/90 ring-1 ring-white/5">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${probWidth}%` }}
            transition={{ duration: 0.65, ease: "easeOut" }}
            className={`h-full rounded-full bg-gradient-to-r ${accent}`}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Position
          </div>
          <div className="mt-1 font-medium text-slate-200">
            P{formatWhole(driver.position_x)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Gap
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatGap(driver.gap_to_leader_seconds)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Compound
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {driver.compound_x}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Tyre Life
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatWhole(driver.tyre_life_x)} laps
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Stint
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatWhole(driver.stint_x)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Number
          </div>
          <div className="mt-1 font-medium text-slate-200">
            #{formatWhole(driver.driver_number)}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function CompactDriverRow({
  driver,
  rank,
  accent = "from-white to-slate-300",
}: {
  driver: DriverRow;
  rank: number;
  accent?: string;
}) {
  const safeProb = Math.max(0, Math.min(1, driver.win_probability));
  const barWidth = Math.max(safeProb * 100, 2);

  return (
    <motion.div
      whileHover={{ y: -1, scale: 1.005 }}
      className="rounded-[18px] border border-white/8 bg-slate-900/70 px-4 py-3 transition-all hover:border-white/15"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg bg-white/5 text-xs font-semibold text-slate-200 ring-1 ring-white/10">
            P{rank}
          </div>

          <div className="min-w-0">
            <div className="font-heading truncate text-sm font-semibold text-white">
              {formatDriverName(driver.driver)}
            </div>
            <div className="mt-0.5 text-xs text-slate-400">
              Gap {formatGap(driver.gap_to_leader_seconds)}
            </div>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-heading text-sm font-semibold text-white">
            {formatPercent(safeProb)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Win probability
          </div>
        </div>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800/90">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${barWidth}%` }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className={`h-full rounded-full bg-gradient-to-r ${accent}`}
        />
      </div>
    </motion.div>
  );
}
