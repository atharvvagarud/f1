// E4 local explanation panel (Phase-8 E4).
//
// Exact decomposition of one frozen winner score in model log-odds for one
// expanded checkpoint driver. Numeric evidence is visually separated from the
// factual identity header: the model input value is never described as a cause
// and never converted into a win-probability percentage. Missing / imputed
// inputs are marked rather than hidden.

"use client";

import { useState } from "react";

import type { LocalContribution } from "@/lib/v2";
import { useLocalExplanation } from "@/features/replay/hooks/useLocalExplanation";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { formatProbability } from "@/features/replay/lib/replayMachine";
import {
  contributionArrow,
  directionWord,
  formatLogOdds,
  inputStateMarker,
  omittedNote,
} from "@/features/replay/lib/localExplanation";
import { SemanticsNote } from "@/components/ui/Panel";

function ContributionRow({ row }: { row: LocalContribution }) {
  const marker = inputStateMarker(row.input_state);
  return (
    <li
      className="flex items-baseline gap-2 border-b border-ink-800 py-1 font-data text-[12px] tabular-nums text-fg"
      title={`${directionWord(row.direction)} (log-odds)`}
    >
      <span className="w-4 shrink-0 text-center text-fg-muted" aria-hidden="true">
        {contributionArrow(row.direction)}
      </span>
      <span className="sr-only">{directionWord(row.direction)}: </span>
      <span className="min-w-0 flex-1 truncate font-ui text-[12px] text-fg">
        {row.canonical_feature}
        {marker ? (
          <span className="ml-2 border border-ink-600 px-1 font-data text-[9px] uppercase tracking-[0.08em] text-fg-dim">
            {marker}
          </span>
        ) : null}
      </span>
      <span className="w-16 shrink-0 text-right font-data text-[12px] text-fg-muted">
        {formatLogOdds(row.log_odds_contribution)}
      </span>
    </li>
  );
}

export function LocalExplanationPanel({
  raceId,
  frameIndex,
  driverId,
}: {
  raceId: string;
  frameIndex: number;
  driverId: string;
}) {
  const view = useLocalExplanation(raceId, frameIndex, driverId);
  const [showTechnical, setShowTechnical] = useState(false);

  return (
    <div className="border-t border-ink-700 bg-ink-950 px-3 py-3">
      <p className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-fg">
        Model log-odds — key inputs
      </p>
      <p className="mt-1 font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
        {readableDriverId(driverId)} · frame {frameIndex} · additive model
        decomposition · independent per-driver binary estimate
      </p>

      {view.kind === "loading" ? (
        <p role="status" className="mt-2 font-data text-[11px] text-fg-muted">
          Loading local explanation…
        </p>
      ) : null}

      {view.kind === "unavailable" ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-warn">
          Explanation unavailable for this checkpoint
          {view.reason ? ` (${view.reason})` : ""}.
        </p>
      ) : null}

      {view.kind === "not_observable" ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-muted">
          This driver has no observable state at this checkpoint, so no local
          model explanation exists.
        </p>
      ) : null}

      {view.kind === "error" ? (
        <p role="alert" className="mt-2 font-data text-[11px] leading-5 text-fg">
          {view.message}
        </p>
      ) : null}

      {view.kind === "ready" ? (
        <div className="mt-2 flex flex-col gap-2">
          <p className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
            Model probability ·{" "}
            <span className="text-fg-muted">
              {formatProbability(view.explanation.probability) ?? "n/a"} (model
              logit {view.explanation.logit.toFixed(3)})
            </span>
          </p>

          {view.explanation.top_positive.length > 0 ? (
            <div>
              <p className="font-data text-[10px] uppercase tracking-[0.12em] text-fg-muted">
                Increased model log-odds
              </p>
              <ul className="mt-1 flex flex-col">
                {view.explanation.top_positive.map((row) => (
                  <ContributionRow key={row.canonical_feature} row={row} />
                ))}
              </ul>
            </div>
          ) : null}

          {view.explanation.top_negative.length > 0 ? (
            <div>
              <p className="font-data text-[10px] uppercase tracking-[0.12em] text-fg-muted">
                Decreased model log-odds
              </p>
              <ul className="mt-1 flex flex-col">
                {view.explanation.top_negative.map((row) => (
                  <ContributionRow key={row.canonical_feature} row={row} />
                ))}
              </ul>
            </div>
          ) : null}

          <SemanticsNote>
            Values are additive model log-odds contributions, not
            win-probability increments.{" "}
            {omittedNote(view.explanation.accounting)}
          </SemanticsNote>

          <button
            type="button"
            className="self-start border border-ink-700 px-2 py-1 font-data text-[10px] uppercase tracking-[0.12em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg"
            aria-expanded={showTechnical}
            onClick={() => setShowTechnical((value) => !value)}
          >
            {showTechnical ? "Hide technical detail" : "Technical detail"}
          </button>

          {showTechnical ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-data text-[11px] tabular-nums text-fg-muted">
              <dt>Intercept</dt>
              <dd className="text-right">{formatLogOdds(view.explanation.intercept)}</dd>
              <dt>Reconstructed logit</dt>
              <dd className="text-right">{view.explanation.logit.toFixed(6)}</dd>
              <dt>Residual</dt>
              <dd className="text-right">
                {view.explanation.reconstruction.residual.toExponential(2)}
              </dd>
              <dt>Cached probability</dt>
              <dd className="text-right">
                {view.explanation.cached_probability === null
                  ? "n/a"
                  : view.explanation.cached_probability.toPrecision(6)}
              </dd>
              <dt>Model</dt>
              <dd className="truncate text-right">
                {view.explanation.model_identity.estimator_class} ·{" "}
                {view.explanation.model_identity.feature_set}/
                {view.explanation.model_identity.feature_set_version}
              </dd>
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
