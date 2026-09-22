"use client";

// Prediction route (UI2). Composition only: page context, control strip,
// loading/error/empty states, the primary decision block and the result tabs.
// Selection state, request flow and result shape live in usePrediction and
// predictionTransforms; no prediction semantics are computed here.

import { PredictionControls } from "@/components/prediction/PredictionControls";
import PredictionTabs from "@/components/prediction/PredictionTabs";
import { PredictionDecision } from "@/features/prediction/components/PredictionDecision";
import {
  PredictionCheckpoints,
  PredictionField,
  PredictionTrend,
} from "@/features/prediction/components/PredictionResultPanels";
import { usePrediction } from "@/features/prediction/hooks/usePrediction";
import {
  buildChartRows,
  buildPredictionView,
} from "@/features/prediction/lib/predictionTransforms";

export default function HomePage() {
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
  } = usePrediction();

  const view = hasPrediction
    ? buildPredictionView(mode, model, event, year, ensembleResult, singleResult)
    : null;
  const chartRows = view
    ? buildChartRows(mode, model, ensembleResult, singleResult)
    : {};

  // Persistent polite status for async completion, mirroring Replay and
  // Simulator. The transient loading paragraph no longer owns the live region,
  // so the "ready" transition is announced instead of silently swapping out.
  const statusMessage = loading
    ? "Running prediction across model checkpoints…"
    : view
      ? "Prediction ready."
      : "";

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header className="border-b border-ink-700 pb-4">
        <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-muted">
          Race intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-fg">
          Winner prediction
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
          Read the frozen winner models at their recorded checkpoints for a
          served historical race. Every driver value is an independent binary
          win probability, not a share of the race.
        </p>
      </header>

      <p role="status" className="sr-only">
        {statusMessage}
      </p>

      <div className="mt-4">
        <PredictionControls
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

      {error ? (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={handlePredict}
            disabled={loading}
            className="h-8 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:text-fg disabled:opacity-50"
          >
            Retry
          </button>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-4 border border-ink-700 bg-ink-900 px-4 py-3 font-data text-[12px] text-fg-muted">
          Running prediction across model checkpoints…
        </p>
      ) : null}

      {view ? (
        <div className="mt-4 space-y-4">
          <PredictionDecision view={view} />

          <div>
            <PredictionTabs
              activeTab={activeTab}
              setActiveTab={setActiveTab}
            />
            <div className="mt-4">
              <section
                role="tabpanel"
                id="pred-panel-field"
                aria-labelledby="pred-tab-field"
                hidden={activeTab !== "field"}
                tabIndex={0}
              >
                <PredictionField view={view} />
              </section>
              <section
                role="tabpanel"
                id="pred-panel-checkpoints"
                aria-labelledby="pred-tab-checkpoints"
                hidden={activeTab !== "checkpoints"}
                tabIndex={0}
              >
                <PredictionCheckpoints view={view} />
              </section>
              <section
                role="tabpanel"
                id="pred-panel-probability"
                aria-labelledby="pred-tab-probability"
                hidden={activeTab !== "probability"}
                tabIndex={0}
              >
                <PredictionTrend
                  chartRows={chartRows}
                  meta={
                    view.mode === "ensemble"
                      ? `${view.field.length} models`
                      : view.modeLabel
                  }
                />
              </section>
            </div>
          </div>
        </div>
      ) : !loading && !error ? (
        <div className="mt-4 border border-ink-700 bg-ink-900 px-4 py-6">
          <p className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
            No prediction loaded
          </p>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-fg-muted">
            Choose a season and Grand Prix above, then run a prediction to read
            the frozen models&apos; winner estimates at each recorded
            checkpoint.
          </p>
        </div>
      ) : null}
    </div>
  );
}
