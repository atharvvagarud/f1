// E5 prediction-change panel (Phase-8 E5).
//
// Exact change in the frozen winner score between a selected checkpoint and
// the driver's PREVIOUS checkpoint. Feature rows are additive model log-odds
// CONTRIBUTION CHANGES: they are never win-probability increments. The only
// percentage-point number shown is the overall model-prediction change, which
// the nonlinear sigmoid prevents from being split per feature.
//
// This panel is the CHANGE view ("what changed in model contribution space
// since the previous checkpoint?"). The Winner model panel carries the LOCAL
// view ("what contributes to the score now?").

"use client";

import type { TimelineChangeContribution } from "@/lib/v2";
import { useTimelineChange } from "@/features/replay/hooks/useTimelineChange";
import {
  changeOmittedNote,
  deltaArrow,
  deltaWord,
  formatLogOdds,
  formatPercentagePoints,
  formatProbabilityPercent,
  transitionMarker,
} from "@/features/replay/lib/timelineChange";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { SemanticsNote } from "@/components/ui/Panel";

function ChangeRow({ row }: { row: TimelineChangeContribution }) {
  const marker = transitionMarker(row.transition);
  const delta = row.contribution_delta;
  return (
    <li
      className="flex items-baseline gap-2 border-b border-ink-800 py-1 font-data text-[12px] tabular-nums text-fg"
      title={deltaWord(delta)}
    >
      <span className="w-4 shrink-0 text-center text-fg-muted" aria-hidden="true">
        {deltaArrow(delta)}
      </span>
      <span className="sr-only">{deltaWord(delta)}: </span>
      <span className="min-w-0 flex-1 truncate font-ui text-[12px] text-fg">
        {row.canonical_feature}
        {marker ? (
          <span className="ml-2 border border-ink-600 px-1 font-data text-[9px] uppercase tracking-[0.08em] text-fg-dim">
            {marker}
          </span>
        ) : null}
      </span>
      <span className="w-16 shrink-0 text-right font-data text-[12px] text-fg-muted">
        {formatLogOdds(delta)}
      </span>
    </li>
  );
}

function reasonMessage(reason: string | null): string {
  if (reason === "DRIVER_NOT_OBSERVABLE_AT_PREVIOUS_CHECKPOINT" ||
      reason === "NULL_PROBABILITY_AT_PREVIOUS_CHECKPOINT") {
    return "This driver has no evaluated probability at the previous " +
      "checkpoint, so there is no valid two-point model change.";
  }
  if (reason === "DRIVER_NOT_OBSERVABLE_AT_SELECTED_CHECKPOINT" ||
      reason === "NULL_PROBABILITY_AT_SELECTED_CHECKPOINT") {
    return "This driver has no evaluated probability at the selected " +
      "checkpoint, so there is no valid two-point model change.";
  }
  if (reason === "DRIVER_ABSENT_AT_PREVIOUS_CHECKPOINT") {
    return "This driver is absent from the previous checkpoint roster.";
  }
  return "A two-point model change is not available for this driver.";
}

export function ChangeExplanationPanel({
  raceId,
  frameIndex,
  driverId,
  driverIds,
  onSelectDriver,
}: {
  raceId: string;
  frameIndex: number;
  driverId: string | null;
  driverIds: string[];
  onSelectDriver: (driverId: string) => void;
}) {
  const view = useTimelineChange(raceId, frameIndex, driverId);

  return (
    <div className="border-t border-ink-700 pt-3">
      <p className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-fg">
        Model score change — since the previous checkpoint
      </p>
      <p className="mt-1 font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
        Change view · additive model log-odds deltas · independent per-driver
        binary estimate
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label
          className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim"
          htmlFor="change-driver-select"
        >
          Driver
        </label>
        <select
          id="change-driver-select"
          value={driverId ?? ""}
          onChange={(e) => onSelectDriver(e.target.value)}
          className="h-8 border border-ink-700 bg-ink-950 px-2 font-data text-[11px] text-fg focus-visible:border-ink-600"
        >
          <option value="">— choose a driver —</option>
          {driverIds.map((id) => (
            <option key={id} value={id}>
              {readableDriverId(id)}
            </option>
          ))}
        </select>
        {view.kind === "no_previous" ? (
          <span className="font-data text-[11px] text-fg-dim">
            first checkpoint — no previous comparison
          </span>
        ) : null}
      </div>

      {view.kind === "idle" ? (
        <p className="mt-2 font-data text-[11px] text-fg-dim">
          Select a driver to compare this checkpoint with the previous one.
        </p>
      ) : null}

      {view.kind === "loading" ? (
        <p role="status" className="mt-2 font-data text-[11px] text-fg-muted">
          Loading change explanation…
        </p>
      ) : null}

      {view.kind === "no_previous" ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-muted">
          No previous prediction checkpoint exists for this selection, so no
          model change is defined. No baseline is fabricated.
        </p>
      ) : null}

      {view.kind === "comparison_unavailable" ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-muted">
          {reasonMessage(view.reason)}
        </p>
      ) : null}

      {view.kind === "unavailable" ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-warn">
          Prediction cache unavailable for this checkpoint
          {view.reason ? ` (${view.reason})` : ""}.
        </p>
      ) : null}

      {view.kind === "error" ? (
        <p role="alert" className="mt-2 font-data text-[11px] leading-5 text-fg">
          {view.message}
        </p>
      ) : null}

      {view.kind === "ready" ? (
        <div className="mt-2 flex flex-col gap-2">
          <p className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
            Exact checkpoints · frame{" "}
            {view.change.identity.from_frame_index ?? "—"} → frame{" "}
            {view.change.identity.to_frame_index}
          </p>
          <div className="font-data text-[11px] tabular-nums text-fg-muted">
            <p>
              P{" "}
              <span className="text-fg">
                {formatProbabilityPercent(view.change.from_probability) ?? "n/a"}
              </span>{" "}
              →{" "}
              <span className="text-fg">
                {formatProbabilityPercent(view.change.to_probability) ?? "n/a"}
              </span>{" "}
              <span className="text-fg-dim">
                Δ {formatPercentagePoints(view.change.probability_delta) ?? "n/a"}
              </span>
            </p>
            <p>
              LOGIT{" "}
              <span className="text-fg">
                {view.change.from_logit === null
                  ? "n/a"
                  : view.change.from_logit.toFixed(3)}
              </span>{" "}
              →{" "}
              <span className="text-fg">
                {view.change.to_logit === null
                  ? "n/a"
                  : view.change.to_logit.toFixed(3)}
              </span>{" "}
              <span className="text-fg-dim">
                Δ {view.change.logit_delta === null
                  ? "n/a"
                  : formatLogOdds(view.change.logit_delta)}
              </span>
            </p>
          </div>

          {view.change.top_positive.length > 0 ? (
            <div>
              <p className="font-data text-[10px] uppercase tracking-[0.12em] text-fg-muted">
                Increased model log-odds
              </p>
              <ul className="mt-1 flex flex-col">
                {view.change.top_positive.map((row) => (
                  <ChangeRow key={row.canonical_feature} row={row} />
                ))}
              </ul>
            </div>
          ) : null}

          {view.change.top_negative.length > 0 ? (
            <div>
              <p className="font-data text-[10px] uppercase tracking-[0.12em] text-fg-muted">
                Decreased model log-odds
              </p>
              <ul className="mt-1 flex flex-col">
                {view.change.top_negative.map((row) => (
                  <ChangeRow key={row.canonical_feature} row={row} />
                ))}
              </ul>
            </div>
          ) : null}

          {view.change.accounting ? (
            <SemanticsNote>
              Feature rows are additive model log-odds contribution changes
              between the two checkpoints, not win-probability increments.{" "}
              {changeOmittedNote(view.change.accounting)}
            </SemanticsNote>
          ) : null}

          <p className="font-data text-[10px] leading-5 text-fg-dim">
            The Winner model panel shows the local decomposition (what
            contributes to the score now); this change view shows what changed
            in model contribution space between checkpoints.
          </p>
        </div>
      ) : null}
    </div>
  );
}
