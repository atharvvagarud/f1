// Selected-driver historical telemetry (V3.10F).
//
// Progressive disclosure over the causal selectors: LAP/SECTORS and TYRE
// HISTORY each live behind a native <details> disclosure that defaults
// CLOSED. The component receives one race-scoped corpus plus the replay
// clock T and renders SELECTOR OUTPUT ONLY — never corpus totals, never
// future rows, never future-derived baselines.
//
// Completed laps only (final values appear together at the lap's
// observation boundary); the in-progress lap shows its number with values
// explicitly unavailable. Deltas are descriptive differences vs the best
// completed lap so far — never causal claims, never qualitative labels.
// Missing renders as em-dash, never zero.

"use client";

import { useMemo } from "react";
import type { DriverRaceState } from "@/lib/v2";
import { useDriverTelemetry } from "@/features/pit-wall/hooks/useDriverTelemetry";
import {
  formatDelta,
  formatLapTime,
  formatSectorTime,
  lapDeltaVsReference,
  selectCompletedDriverLaps,
  selectCurrentLapState,
  selectRecentLaps,
  selectReferenceLap,
  selectStintHistory,
  type ReferenceLap,
  type TelemetryLap,
} from "@/features/pit-wall/lib/telemetry";

const DASH = "—";
const RECENT_COUNT = 5;

const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";
const valueClass = "font-data text-[13px] text-fg tabular-nums";
const summaryClass =
  "cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus";

function text(value: string | null): string {
  return value ?? DASH;
}

function LapRow({
  lap,
  reference,
  completed,
}: {
  lap: TelemetryLap;
  reference: ReferenceLap | null;
  completed: readonly TelemetryLap[];
}) {
  const delta = lapDeltaVsReference(lap, reference, completed);
  const isReference =
    reference !== null && lap.lapNumber === reference.lapNumber;
  return (
    <li className="border-t border-ink-700 py-2 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-data text-[13px] font-semibold text-fg tabular-nums">
          LAP {lap.lapNumber}
        </span>
        <span className={valueClass}>
          {text(formatLapTime(lap.lapTimeS))}
        </span>
        {isReference ? (
          <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Reference
          </span>
        ) : null}
        {lap.pitEntry === true || lap.pitExit === true ? (
          <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Pit lap
          </span>
        ) : null}
        {lap.generated === true ? (
          <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Synthetic source row
          </span>
        ) : null}
      </div>
      <dl className="mt-1 grid grid-cols-3 gap-x-4 gap-y-1 sm:grid-cols-6">
        <div>
          <dt className={labelClass}>S1</dt>
          <dd className={valueClass}>{text(formatSectorTime(lap.sector1S))}</dd>
        </div>
        <div>
          <dt className={labelClass}>S2</dt>
          <dd className={valueClass}>{text(formatSectorTime(lap.sector2S))}</dd>
        </div>
        <div>
          <dt className={labelClass}>S3</dt>
          <dd className={valueClass}>{text(formatSectorTime(lap.sector3S))}</dd>
        </div>
        <div>
          <dt className={labelClass}>Δ lap</dt>
          <dd className={valueClass}>
            {isReference ? "ref" : text(formatDelta(delta.lapS))}
          </dd>
        </div>
        <div>
          <dt className={labelClass}>Δ S1/S2</dt>
          <dd className={valueClass}>
            {isReference
              ? "ref"
              : `${text(formatDelta(delta.sector1S))} / ${text(formatDelta(delta.sector2S))}`}
          </dd>
        </div>
        <div>
          <dt className={labelClass}>Δ S3</dt>
          <dd className={valueClass}>
            {isReference ? "ref" : text(formatDelta(delta.sector3S))}
          </dd>
        </div>
      </dl>
    </li>
  );
}

export function DriverTelemetry({
  raceId,
  driverId,
  drivers,
  tS,
  leaderLap,
  raceComplete,
}: {
  raceId: string;
  driverId: string;
  drivers: DriverRaceState[];
  tS: number;
  leaderLap: number | null;
  raceComplete: boolean;
}) {
  const { status, corpus, retry } = useDriverTelemetry(raceId);

  const view = useMemo(() => {
    if (corpus === null || corpus.raceId !== raceId) return null;
    const completed = selectCompletedDriverLaps(corpus, driverId, tS);
    const recent = selectRecentLaps(completed, RECENT_COUNT);
    const reference = selectReferenceLap(completed);
    const frameDriver =
      drivers.find((d) => d.driver_id === driverId) ?? null;
    const maxCompleted =
      completed.length === 0
        ? null
        : completed.reduce((m, l) => Math.max(m, l.lapNumber), 0);
    const current = selectCurrentLapState({
      maxCompletedLap: maxCompleted,
      leaderLap,
      raceComplete,
      hasFrameEvidence: frameDriver !== null,
    });
    const stints = selectStintHistory(
      corpus,
      driverId,
      tS,
      frameDriver?.compound != null
        ? frameDriver.compound.toUpperCase()
        : null,
      frameDriver?.stint_number ?? null,
      frameDriver?.observed_lap_number ?? null,
    );
    return { completed, recent, reference, current, stints };
  }, [corpus, raceId, driverId, drivers, tS, leaderLap, raceComplete]);

  return (
    <div className="mt-4 border-t border-ink-700 pt-3">
      <h3 className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-fg">
        Telemetry
      </h3>
      {status === "loading" ? (
        <p
          aria-live="polite"
          className="mt-2 font-data text-[12px] leading-5 text-fg-dim"
        >
          Loading telemetry…
        </p>
      ) : status === "unavailable" || view === null ? (
        <div className="mt-2">
          <p className="font-data text-[12px] leading-5 text-fg-dim">
            Telemetry unavailable for this race — not the same as no laps.
          </p>
          <button
            type="button"
            onClick={retry}
            className="mt-2 h-9 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
          >
            Retry telemetry
          </button>
        </div>
      ) : (
        <div className="mt-2 space-y-3">
          <details>
            <summary className={summaryClass}>
              Lap / sectors
            </summary>
            <div className="mt-2">
              {view.completed.length === 0 ? (
                <p className="font-data text-[12px] leading-5 text-fg-dim">
                  {view.current.kind === "no-evidence"
                    ? "No observed data for this driver at this frame. The selection is kept."
                    : "No completed laps observed yet at this frame."}
                </p>
              ) : (
                <div>
                  <p className="font-data text-[11px] leading-5 text-fg-dim">
                    Last {Math.min(RECENT_COUNT, view.completed.length)}{" "}
                    completed lap
                    {view.completed.length === 1 ? "" : "s"}.
                    {view.reference !== null
                      ? ` Reference: best completed lap so far, LAP ${view.reference.lapNumber}. Deltas are descriptive differences, not explanations.`
                      : " No reference lap yet — no recorded lap time."}
                  </p>
                  <ul className="mt-2 border-t border-ink-700 pt-2">
                    {view.recent.map((lap) => (
                      <LapRow
                        key={lap.lapNumber}
                        lap={lap}
                        reference={view.reference}
                        completed={view.completed}
                      />
                    ))}
                  </ul>
                  <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
                    {view.current.kind === "in-progress"
                      ? `LAP ${view.current.lapNumber} in progress — final time and sectors not yet observed.`
                      : view.current.kind === "replay-end"
                        ? "Replay end — completed laps above are all that was observed."
                        : view.current.kind === "no-new-lap"
                          ? `No completed lap observed since LAP ${view.current.lastCompletedLap ?? DASH} — status unavailable, not estimated.`
                          : "No observed data for this driver at this frame."}
                  </p>
                </div>
              )}
            </div>
          </details>

          <details>
            <summary className={summaryClass}>
              Tyre history
            </summary>
            <div className="mt-2">
              {view.stints.completed.length === 0 &&
              view.stints.active === null ? (
                <p className="font-data text-[12px] leading-5 text-fg-dim">
                  {view.stints.activeUnknown
                    ? "Stint state unavailable at this frame — transition ambiguity, not estimated."
                    : "No completed stints observed yet at this frame."}
                </p>
              ) : (
                <div>
                  <ul className="space-y-2">
                    {view.stints.completed.map((stint) => (
                      <li
                        key={stint.stintNumber}
                        className="font-data text-[12px] leading-5 text-fg tabular-nums"
                      >
                        <span className="font-semibold">
                          STINT {stint.stintNumber}
                        </span>{" "}
                        {stint.compound ?? "UNKNOWN"}
                        {stint.startLap !== null && stint.endLap !== null
                          ? ` · laps ${stint.startLap}–${stint.endLap}${stint.lapCount !== null ? ` · ${stint.lapCount} laps` : ""}`
                          : " · lap range unavailable"}{" "}
                        · completed
                      </li>
                    ))}
                    {view.stints.active !== null ? (
                      <li className="font-data text-[12px] leading-5 text-fg tabular-nums">
                        <span className="font-semibold">
                          STINT {view.stints.active.stintNumber}
                        </span>{" "}
                        {view.stints.active.compound ?? "UNKNOWN"}
                        {view.stints.active.startLap !== null
                          ? ` · lap ${view.stints.active.startLap}–current`
                          : " · start lap unavailable"}
                        {view.stints.active.stintAgeLaps !== null
                          ? ` · stint age ${view.stints.active.stintAgeLaps}`
                          : ""}
                        {" · active"}
                      </li>
                    ) : view.stints.activeUnknown ? (
                      <li className="font-data text-[12px] leading-5 text-fg-dim">
                        Current stint unavailable at this frame — transition
                        ambiguity, not estimated.
                      </li>
                    ) : null}
                  </ul>
                  <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
                    Completed stints show full ranges; the active stint shows
                    only facts known at this frame. Future stints are never
                    listed. Stint age counts observed laps in the stint.
                  </p>
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
