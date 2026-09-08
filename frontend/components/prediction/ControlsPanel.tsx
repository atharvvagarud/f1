"use client";

import { motion } from "motion/react";
import { Gauge } from "lucide-react";

type ControlsPanelProps = {
  year: number;
  years: number[];
  setYear: (value: number) => void;
  event: string;
  events: string[];
  setEvent: (value: string) => void;
  mode: "ensemble" | "single";
  setMode: (value: "ensemble" | "single") => void;
  model: "logreg" | "hgb" | "xgboost";
  setModel: (value: "logreg" | "hgb" | "xgboost") => void;
  loading: boolean;
  handlePredict: () => void;
};

export default function ControlsPanel({
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
}: ControlsPanelProps) {
  return (
    <motion.aside
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: 0.06 }}
      className="col-span-12 rounded-[30px] border border-white/10 bg-slate-900/85 p-6 shadow-[0_30px_80px_rgba(0,0,0,0.28)] lg:col-span-4"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-2xl bg-white/5 p-3 ring-1 ring-white/10">
          <Gauge className="h-5 w-5 text-white" />
        </div>
        <div>
          <h2 className="font-heading text-xl font-semibold">Controls</h2>
          <p className="text-sm text-slate-400">
            Select race context and run the prediction.
          </p>
        </div>
      </div>

      <div className="mt-6 space-y-5">
        <div>
          <label className="mb-2 block text-sm font-medium text-slate-300">
            Year
          </label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-full rounded-2xl border border-white/10 bg-slate-800/90 px-4 py-3 text-white outline-none transition focus:border-white/20 focus:ring-2 focus:ring-white/10"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-slate-300">
            Grand Prix
          </label>
          <select
            value={event}
            onChange={(e) => setEvent(e.target.value)}
            className="w-full rounded-2xl border border-white/10 bg-slate-800/90 px-4 py-3 text-white outline-none transition focus:border-white/20 focus:ring-2 focus:ring-white/10"
          >
            {events.map((ev) => (
              <option key={ev} value={ev}>
                {ev}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-slate-300">
            Mode
          </label>
          <div className="grid grid-cols-2 gap-2 rounded-2xl border border-white/10 bg-slate-800/80 p-1">
            <button
              onClick={() => setMode("ensemble")}
              className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${
                mode === "ensemble"
                  ? "bg-white text-slate-950 shadow-lg shadow-black/20"
                  : "text-slate-300 hover:bg-white/5"
              }`}
            >
              Ensemble
            </button>
            <button
              onClick={() => setMode("single")}
              className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${
                mode === "single"
                  ? "bg-white text-slate-950 shadow-lg shadow-black/20"
                  : "text-slate-300 hover:bg-white/5"
              }`}
            >
              Single model
            </button>
          </div>
        </div>

        {mode === "single" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <label className="mb-2 block text-sm font-medium text-slate-300">
              Model family
            </label>
            <select
              value={model}
              onChange={(e) =>
                setModel(e.target.value as "logreg" | "hgb" | "xgboost")
              }
              className="w-full rounded-2xl border border-white/10 bg-slate-800/90 px-4 py-3 text-white outline-none transition focus:border-white/20 focus:ring-2 focus:ring-white/10"
            >
              <option value="logreg">Logistic Regression</option>
              <option value="hgb">HistGradientBoosting</option>
              <option value="xgboost">XGBoost</option>
            </select>
          </motion.div>
        )}

        <motion.button
          whileHover={loading ? undefined : { scale: 1.015, y: -1 }}
          whileTap={loading ? undefined : { scale: 0.985 }}
          onClick={handlePredict}
          disabled={loading}
          className={`w-full rounded-2xl px-4 py-3.5 font-semibold transition-all ${
            loading
              ? "cursor-not-allowed bg-slate-700 text-slate-300 opacity-70 shadow-none"
              : "bg-white text-slate-950 shadow-[0_10px_30px_rgba(255,255,255,0.08)] hover:bg-slate-200 hover:shadow-[0_15px_40px_rgba(255,255,255,0.10)]"
          }`}
        >
          {loading ? "Running prediction..." : "Run Race Prediction"}
        </motion.button>

        {loading && (
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-200">
            Loading race telemetry and computing prediction outputs...
          </div>
        )}
      </div>
    </motion.aside>
  );
}
