"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePrediction } from "@/features/prediction/hooks/usePrediction";
import PredictionHero from "@/features/prediction/components/PredictionHero";
import EnsembleResults from "@/features/prediction/components/EnsembleResults";
import SingleResults from "@/features/prediction/components/SingleResults";
import PredictionTabs from "@/components/prediction/PredictionTabs";
import ControlsPanel from "@/components/prediction/ControlsPanel";

// Prediction route: composes the prediction feature. All selection state,
// data fetching and request flow live in usePrediction; hero, tab sections
// and controls are feature/components. This file owns page layout only.

export default function HomePage() {
  const prediction = usePrediction();
  const {
    year,
    years,
    setYear,
    event,
    events,
    setEvent,
    mode,
    setMode,
    model,
    setModel,
    loading,
    ensembleResult,
    singleResult,
    error,
    activeTab,
    setActiveTab,
    handlePredict,
    hasPrediction,
  } = prediction;

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div
        className={`mx-auto max-w-7xl px-6 ${
          hasPrediction
            ? "py-10"
            : "min-h-screen flex items-center justify-center"
        }`}
      >
        <div className="mb-4 flex w-full justify-end">
          <Link
            href="/replay"
            className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 hover:border-white/25"
          >
            Historical replay →
          </Link>
        </div>
        {error && (
          <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-slate-200">
            {error}
          </div>
        )}
        <div className="w-full">
          <div className="mx-auto grid max-w-6xl grid-cols-12 gap-6">
            <PredictionHero
              mode={mode}
              model={model}
              event={event}
              year={year}
              ensembleResult={ensembleResult}
              singleResult={singleResult}
            />

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
            <EnsembleResults
              ensembleResult={ensembleResult}
              event={event}
              year={year}
              activeTab={activeTab}
            />
          )}

          {mode === "single" && singleResult && (
            <SingleResults
              singleResult={singleResult}
              model={model}
              event={event}
              year={year}
              activeTab={activeTab}
            />
          )}
        </motion.section>
      </div>
    </main>
  );
}
