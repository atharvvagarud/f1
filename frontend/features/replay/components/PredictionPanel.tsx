// Cached winner-prediction panel (Phase-5 R5).
//
// Checkpoint honesty: non-checkpoint frames never trigger a request and say
// so; 503 cache absence is an expected, non-fatal state. HIT values render
// verbatim as independent binary estimates — horizontal bars (never a pie),
// no normalization, aggregates >100% shown as valid, nulls never 0%.

"use client";

import type { PredictionView } from "@/features/replay/hooks/useReplay";
import {
  formatProbability,
  sumProbabilities,
} from "@/features/replay/lib/replayMachine";
import { readableDriverId } from "@/features/replay/components/StandingsTable";

export function PredictionPanel({
  prediction,
  isCheckpoint,
  checkpointReasons,
}: {
  prediction: PredictionView;
  isCheckpoint: boolean;
  checkpointReasons: string[];
}) {
  return (
    <section aria-label="Cached winner prediction" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-sm font-bold uppercase tracking-[0.16em] text-slate-300">
          Winner model
        </h2>
        {isCheckpoint ? (
          <span className="rounded bg-sky-500/15 px-2 py-0.5 text-[11px] font-bold tracking-[0.1em] text-sky-300 ring-1 ring-sky-500/30">
            PREDICTION CHECKPOINT{checkpointReasons.length > 0 ? ` • ${checkpointReasons.join(" + ")}` : ""}
          </span>
        ) : (
          <span className="rounded bg-white/5 px-2 py-0.5 text-[11px] font-semibold tracking-[0.1em] text-slate-500 ring-1 ring-white/10">
            NO MODEL CHECKPOINT AT THIS FRAME
          </span>
        )}
      </div>

      {prediction.kind === "none" && (
        <p className="text-sm leading-6 text-slate-400">
          {isCheckpoint
            ? "Awaiting cached prediction for this checkpoint."
            : "Factual frame only — model checkpoints are sparse. Step to a checkpoint frame to see winner estimates."}
        </p>
      )}

      {prediction.kind === "loading" && (
        <p role="status" className="text-sm text-slate-400">
          Loading cached prediction…
        </p>
      )}

      {prediction.kind === "unavailable" && (
        <div role="status" className="rounded-md border border-white/10 bg-white/5 px-3 py-2">
          <p className="text-sm font-semibold text-slate-200">Prediction unavailable</p>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Historical prediction cache has not been generated for this
            checkpoint{prediction.reason ? ` (${prediction.reason})` : ""}. Factual
            replay is unaffected.
          </p>
        </div>
      )}

      {prediction.kind === "error" && (
        <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2">
          <p className="text-sm text-red-200">{prediction.message}</p>
        </div>
      )}

      {prediction.kind === "hit" && (
        <PredictionHit prediction={prediction.response.prediction} />
      )}
    </section>
  );
}

function PredictionHit({
  prediction,
}: {
  prediction: {
    probability_semantics: string;
    probability_semantics_note: string;
    predictions: {
      driver_id: string;
      observable: boolean;
      observed_position: number | null;
      winner_probability: number | null;
      unavailable_reason: string | null;
    }[];
  };
}) {
  const ranked = [...prediction.predictions].sort(
    (a, b) => (b.winner_probability ?? -1) - (a.winner_probability ?? -1),
  );
  const total = sumProbabilities(ranked.map((p) => p.winner_probability));
  const scale = Math.max(...ranked.map((p) => p.winner_probability ?? 0), 0);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
        Win probability •{" "}
        <span className="text-slate-400">
          independent binary model estimates (Σ {(total * 100).toFixed(1)}% — valid, not shares)
        </span>
      </p>
      <ol className="flex flex-col gap-1.5">
        {ranked.map((entry) => {
          const text = formatProbability(entry.winner_probability);
          const width =
            entry.winner_probability !== null && scale > 0
              ? `${Math.max((entry.winner_probability / scale) * 100, 2)}%`
              : "0%";
          return (
            <li
              key={entry.driver_id}
              className={`flex items-center gap-2 font-mono text-[13px] tabular-nums ${
                entry.winner_probability === null ? "opacity-45" : ""
              }`}
            >
              <span className="w-36 shrink-0 truncate font-sans text-xs font-semibold text-slate-200">
                {readableDriverId(entry.driver_id)}
              </span>
              <span className="relative h-4 flex-1 overflow-hidden rounded-sm bg-slate-800">
                <span
                  className="absolute inset-y-0 left-0 rounded-sm bg-sky-500"
                  style={{ width }}
                />
              </span>
              <span className="w-20 shrink-0 text-right text-slate-100">
                {text ?? "n/a"}
              </span>
              {entry.winner_probability === null && (
                <span className="w-24 shrink-0 text-right text-[10px] uppercase tracking-wide text-slate-500">
                  {entry.unavailable_reason ?? "unavailable"}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="text-[11px] leading-5 text-slate-500">
        {prediction.probability_semantics}: {prediction.probability_semantics_note}
      </p>
    </div>
  );
}
