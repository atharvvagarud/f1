"use client";

// Prediction control strip (UI2). Dense workstation controls: labelled selects,
// a native-radio segmented mode control, and a single primary action. Labels
// are programmatically associated via htmlFor/id; no fake telemetry.

import type { ModelId, PredictionMode } from "@/lib/predictionTypes";

type PredictionControlsProps = {
  year: number;
  years: number[];
  setYear: (value: number) => void;
  event: string;
  events: string[];
  setEvent: (value: string) => void;
  mode: PredictionMode;
  setMode: (value: PredictionMode) => void;
  model: ModelId;
  setModel: (value: ModelId) => void;
  loading: boolean;
  handlePredict: () => void;
};

const labelClass =
  "text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const selectClass =
  "h-9 w-full border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg transition-colors focus-visible:border-ink-600 disabled:opacity-50";

export function PredictionControls({
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
  handlePredict,
}: PredictionControlsProps) {
  return (
    <form
      onSubmit={(changeEvent) => {
        changeEvent.preventDefault();
        handlePredict();
      }}
      className="border border-ink-700 bg-ink-900 p-4"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[8rem_minmax(14rem,1fr)_auto_auto]">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="pred-year" className={labelClass}>
            Season
          </label>
          <select
            id="pred-year"
            className={selectClass}
            value={year}
            disabled={loading}
            onChange={(changeEvent) => setYear(Number(changeEvent.target.value))}
          >
            {years.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="pred-event" className={labelClass}>
            Grand Prix
          </label>
          <select
            id="pred-event"
            className={selectClass}
            value={event}
            disabled={loading}
            onChange={(changeEvent) => setEvent(changeEvent.target.value)}
          >
            {events.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
          <legend className={labelClass}>Mode</legend>
          <div className="inline-flex h-9 border border-ink-700">
            {(["ensemble", "single"] as const).map((value, index) => (
              <label
                key={value}
                className={`relative inline-flex cursor-pointer ${
                  index > 0 ? "border-l border-ink-700" : ""
                }`}
              >
                <input
                  type="radio"
                  name="pred-mode"
                  value={value}
                  checked={mode === value}
                  disabled={loading}
                  onChange={() => setMode(value)}
                  className="peer sr-only"
                />
                <span className="flex items-center px-3 text-[11px] uppercase tracking-[0.14em] text-fg-muted peer-checked:bg-ink-600 peer-checked:text-fg peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus">
                  {value === "ensemble" ? "Ensemble" : "Single"}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {mode === "single" ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="pred-model" className={labelClass}>
              Model family
            </label>
            <select
              id="pred-model"
              className={selectClass}
              value={model}
              disabled={loading}
              onChange={(changeEvent) =>
                setModel(changeEvent.target.value as ModelId)
              }
            >
              <option value="logreg">Logistic Regression</option>
              <option value="hgb">HistGradientBoosting</option>
              <option value="xgboost">XGBoost</option>
            </select>
          </div>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-ink-700 pt-4">
        <p className="max-w-xl font-data text-[11px] leading-5 text-fg-dim">
          Selects a served historical race. The prediction reads the frozen
          models at their recorded checkpoints only.
        </p>
        <button
          type="submit"
          disabled={loading || !event}
          className="h-9 border border-signal bg-signal px-4 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-focus transition-colors hover:bg-signal/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running…" : "Run prediction"}
        </button>
      </div>
    </form>
  );
}
