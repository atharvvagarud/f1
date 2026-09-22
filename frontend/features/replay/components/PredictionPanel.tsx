// Cached winner-prediction panel (Phase-5 R5; UI3 model intelligence).
//
// Checkpoint honesty: non-checkpoint frames never trigger a request and say so;
// 503 cache absence is an expected, non-fatal technical state. HIT values
// render verbatim as independent binary estimates — horizontal bars (never a
// pie, never a share), no normalization, aggregates >100% shown as valid,
// nulls never 0%.

"use client";

import type { PredictionView } from "@/features/replay/hooks/useReplay";
import {
  formatProbability,
  sumProbabilities,
} from "@/features/replay/lib/replayMachine";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";

function unavailableState(reason: string | null, scope: string) {
  return (
    <div className="flex flex-col gap-2">
      <div
        role="status"
        className="border border-warn/40 bg-ink-950 px-3 py-2.5"
      >
        <p className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-warn">
          Cache not available
        </p>
        <p className="mt-1 font-data text-[11px] leading-5 text-fg-muted">
          Historical prediction cache has not been generated for {scope}
          {reason ? ` (${reason})` : ""}. Factual replay is unaffected.
        </p>
      </div>
    </div>
  );
}

export function PredictionPanel({
  prediction,
  isCheckpoint,
  checkpointReasons,
}: {
  prediction: PredictionView;
  isCheckpoint: boolean;
  checkpointReasons: string[];
}) {
  const meta = isCheckpoint
    ? `Prediction checkpoint${
        checkpointReasons.length > 0 ? ` · ${checkpointReasons.join(" + ")}` : ""
      }`
    : "No model checkpoint";

  return (
    <Panel>
      <PanelHeader title="Winner model" meta={meta} />

      <div className="px-4 py-3">
        {prediction.kind === "none" &&
          (isCheckpoint ? (
            <p className="font-data text-[11px] leading-5 text-fg-muted">
              Awaiting cached prediction for this checkpoint.
            </p>
          ) : (
            <p className="font-data text-[11px] leading-5 text-fg-muted">
              Factual frame only — model checkpoints are sparse. Step to a
              checkpoint frame to read the frozen winner estimates.
            </p>
          ))}

        {prediction.kind === "loading" && (
          <p
            role="status"
            className="font-data text-[11px] leading-5 text-fg-muted"
          >
            Loading cached prediction…
          </p>
        )}

        {prediction.kind === "unavailable" &&
          unavailableState(prediction.reason, "this race's checkpoints")}

        {prediction.kind === "error" && (
          <div
            role="alert"
            className="border border-danger/40 bg-ink-950 px-3 py-2.5 font-data text-[11px] leading-5 text-fg"
          >
            {prediction.message}
          </div>
        )}

        {prediction.kind === "hit" && (
          <PredictionHit prediction={prediction.response.prediction} />
        )}
      </div>
    </Panel>
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
      <p className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
        Win probability ·{" "}
        <span className="text-fg-muted">
          independent binary estimates (Σ {(total * 100).toFixed(1)}% — valid,
          not shares)
        </span>
      </p>
      <ol className="flex flex-col">
        {ranked.map((entry) => {
          const text = formatProbability(entry.winner_probability);
          const width =
            entry.winner_probability !== null && scale > 0
              ? `${Math.max((entry.winner_probability / scale) * 100, 2)}%`
              : "0%";
          return (
            <li
              key={entry.driver_id}
              className={`flex items-center gap-2 border-b border-ink-700 py-1.5 font-data text-[12px] tabular-nums ${
                entry.winner_probability === null ? "text-fg-dim" : "text-fg"
              }`}
            >
              <span className="w-36 shrink-0 truncate font-ui text-[12px] font-semibold text-fg">
                {readableDriverId(entry.driver_id)}
              </span>
              <span
                className="relative h-3 flex-1 overflow-hidden bg-ink-850"
                aria-hidden="true"
              >
                <span
                  className="absolute inset-y-0 left-0 bg-info"
                  style={{ width }}
                />
              </span>
              <span className="w-20 shrink-0 text-right">
                {text ?? "n/a"}
              </span>
              {entry.winner_probability === null && (
                <span className="w-20 shrink-0 text-right font-ui text-[10px] uppercase tracking-[0.08em] text-fg-dim">
                  {entry.unavailable_reason ?? "unavailable"}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <SemanticsNote>
        {prediction.probability_semantics}: {prediction.probability_semantics_note}{" "}
        Not normalised and not a categorical race distribution.
      </SemanticsNote>
    </div>
  );
}
