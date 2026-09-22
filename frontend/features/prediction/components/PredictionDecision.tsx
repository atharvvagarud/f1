"use client";

// Primary prediction result (UI2): the decision line the analyst reads first.
// Winner, its probability, checkpoint, mode/agreement and comparison against
// the official result, as dense telemetry rather than a hero card. All values
// come from the active result view-model; nothing is fabricated.

import {
  formatDriverName,
  formatPercent,
  titleCaseModelName,
} from "@/lib/predictionHelpers";
import type { PredictionView } from "../lib/predictionTransforms";
import {
  Panel,
  ProbabilityBar,
  SemanticsNote,
  Stat,
} from "./PredictionPrimitives";

function statClass(index: number) {
  const parts: string[] = [];
  if (index % 2 === 1) parts.push("border-l border-ink-700");
  if (index > 0 && index % 2 === 0) parts.push("sm:border-l sm:border-ink-700");
  if (index >= 2) parts.push("border-t border-ink-700 sm:border-t-0");
  return parts.join(" ");
}

export function PredictionDecision({ view }: { view: PredictionView }) {
  const winnerLabel = formatDriverName(view.leader.winner);
  const modelFamily = titleCaseModelName(view.field[0]?.modelKey ?? "");
  const modeHint =
    view.mode === "ensemble" ? "Majority vote of 3 models" : modelFamily;

  const stats: Array<{ label: string; value: string; hint?: string }> = [
    {
      label: "Checkpoint",
      value: `Lap ${view.leader.lap}`,
      hint: "Latest model checkpoint",
    },
    { label: "Mode", value: view.modeLabel, hint: modeHint },
    view.agreementCount !== null
      ? {
          label: "Agreement",
          value: `${view.agreementCount} / 3`,
          hint: "Models aligned",
        }
      : {
          label: "Model",
          value: modelFamily,
          hint: "Active model family",
        },
    {
      label: "Vs actual",
      value:
        view.matched === null ? "—" : view.matched ? "Matched" : "Not matched",
      hint: `Official winner ${formatDriverName(view.actualWinner)}`,
    },
  ];

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 px-4 py-4">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.16em] text-fg-dim">
            Predicted winner
          </p>
          <p className="mt-1 font-display text-3xl font-extrabold tracking-[-0.03em] text-fg sm:text-4xl">
            {winnerLabel}
          </p>
          <p className="mt-1.5 font-data text-[11px] tracking-[0.08em] text-fg-muted">
            {view.leader.winner} · {view.event} ({view.year})
          </p>
        </div>

        <div className="w-full min-w-0 max-w-xs shrink-0 sm:w-auto sm:text-right">
          <p className="font-data text-4xl font-bold tracking-[-0.02em] text-fg tabular-nums sm:text-5xl">
            {formatPercent(view.leader.winProbability)}
          </p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            {view.leader.probabilityLabel}
          </p>
          <ProbabilityBar
            value={view.leader.winProbability}
            className="mt-2 w-full sm:w-52"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 border-t border-ink-700 sm:grid-cols-4">
        {stats.map((stat, index) => (
          <Stat
            key={stat.label}
            label={stat.label}
            value={stat.value}
            hint={stat.hint}
            className={statClass(index)}
          />
        ))}
      </div>

      {view.decisionReason ? (
        <div className="border-t border-ink-700 px-4 py-3">
          <span className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Decision
          </span>
          <p className="mt-1 text-[13px] leading-5 text-fg-muted">
            {view.decisionReason}
          </p>
        </div>
      ) : null}

      <div className="border-t border-ink-700 bg-ink-950/50 px-4 py-3">
        <SemanticsNote>
          Independent binary win probabilities — each value is one model&apos;s
          estimated chance for that driver on its own. Values across drivers are
          not a mutually exclusive race distribution and do not sum to 100%.
        </SemanticsNote>
      </div>
    </Panel>
  );
}
