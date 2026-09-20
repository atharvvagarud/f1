// Win-probability evolution chart (Phase-5 R6).
//
// SVG only (no chart dependency: package.json audited). Renders ACTUAL model
// checkpoints only; lines visually connect consecutive observations for the
// same driver and break at null (never plotted as 0). No stacked/share/pie
// view: INDEPENDENT_BINARY values are not a mutually exclusive distribution.
// The current replay frame is marked separately; between checkpoints no
// current probability is implied.

"use client";

import { useMemo, useState } from "react";
import type { ProbabilityTimelineResponse } from "@/lib/v2";
import type { ProbabilityTimelineView } from "@/features/replay/hooks/useReplay";
import {
  buildChartGeometry,
  checkpointAt,
  currentFrameAlignment,
  defaultVisibleDrivers,
  probabilityAtCheckpoint,
} from "@/features/replay/lib/probabilityTimeline";
import { formatRaceTime, sumProbabilities } from "@/features/replay/lib/replayMachine";

const PALETTE = [
  "#38bdf8", "#f87171", "#4ade80", "#facc15", "#c084fc",
  "#fb923c", "#2dd4bf", "#f472b6", "#a3e635", "#60a5fa",
  "#e879f9", "#fca5a5", "#86efac", "#fde047", "#d8b4fe",
  "#fdba74", "#5eead4", "#f9a8d4", "#bef264", "#93c5fd",
];

export const colorForDriver = (driverId: string): string => {
  let hash = 0;
  for (let i = 0; i < driverId.length; i++) {
    hash = (hash * 31 + driverId.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length];
};

export function ProbabilityTimelineChart({
  view,
  frameIndex,
}: {
  view: ProbabilityTimelineView;
  frameIndex: number;
}) {
  const timeline = view.kind === "ready" ? view.timeline : null;
  // Display-only visibility overrides; the complete series is never altered.
  // The component is keyed by race in ReplayView, so overrides reset on race
  // change without an effect.
  const [visibilityOverrides, setVisibilityOverrides] = useState<
    Record<string, boolean>
  >({});
  const [selectedOverride, setSelectedOverride] = useState<number | null>(null);
  const defaultVisible = useMemo(
    () => (timeline ? defaultVisibleDrivers(timeline, 5) : []),
    [timeline],
  );
  const isVisible = (driverId: string): boolean =>
    visibilityOverrides[driverId] ?? defaultVisible.includes(driverId);

  const alignment = useMemo(
    () => (timeline ? currentFrameAlignment(timeline, frameIndex) : null),
    [timeline, frameIndex],
  );

  if (view.kind === "idle" || view.kind === "loading") {
    return (
      <Shell>
        <p role="status" className="text-sm text-slate-400">
          Loading probability timeline…
        </p>
      </Shell>
    );
  }

  if (view.kind === "unavailable") {
    return (
      <Shell>
        <div role="status" className="rounded-md border border-white/10 bg-white/5 px-3 py-2">
          <p className="text-sm font-semibold text-slate-200">
            Probability timeline unavailable.
          </p>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Historical prediction cache has not been generated for this race
            {view.reason ? ` (${view.reason})` : ""}. Factual replay is
            unaffected.
          </p>
        </div>
      </Shell>
    );
  }

  if (view.kind === "error") {
    return (
      <Shell>
        <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {view.message}
        </div>
      </Shell>
    );
  }

  if (!timeline) return null;

  const visibleDrivers = timeline.driver_series
    .map((s) => s.driver_id)
    .filter(isVisible);
  const geometry = buildChartGeometry(timeline, visibleDrivers, {
    width: 720,
    height: 280,
  });
  const exact = checkpointAt(timeline, frameIndex);
  const detailsFrame = selectedOverride ?? exact?.frame_index ?? null;
  const selected =
    detailsFrame !== null ? checkpointAt(timeline, detailsFrame) : null;
  const flagCheckpoints = new Set(
    timeline.checkpoints
      .filter((c) => c.reasons.includes("FLAG_TRANSITION"))
      .map((c) => c.frame_index),
  );
  const checkpointOrdinal = new Map<number, number>();
  timeline.checkpoints.forEach((c, i) => checkpointOrdinal.set(c.frame_index, i));
  const xPos = (ordinal: number) =>
    geometry.plot.x +
    (geometry.xMax === 0 ? 0 : (ordinal / geometry.xMax) * geometry.plot.width);

  return (
    <Shell>
      <p className="text-[11px] leading-5 text-slate-500">
        {timeline.probability_semantics} — each line is an independent binary
        estimate; values are shown verbatim and are not shares (their sum need
        not be 100%). Points exist only where the frozen model was evaluated.
      </p>

      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label="Win probability evolution across model checkpoints"
          viewBox={`0 0 ${geometry.width} ${geometry.height}`}
          className="min-w-[640px] w-full"
        >
          {geometry.yTicks.map((tick) => (
            <g key={`y-${tick.value}`}>
              <line
                x1={geometry.plot.x}
                x2={geometry.plot.x + geometry.plot.width}
                y1={tick.y}
                y2={tick.y}
                stroke="#1e293b"
                strokeWidth={1}
              />
              <text x={4} y={tick.y + 3} fill="#64748b" fontSize={10}>
                {tick.label}
              </text>
            </g>
          ))}
          {geometry.xTicks.map((tick) => (
            <text
              key={`x-${tick.frameIndex}`}
              x={tick.x}
              y={geometry.height - 8}
              fill="#64748b"
              fontSize={10}
              textAnchor="middle"
            >
              {tick.label}
            </text>
          ))}

          {[...flagCheckpoints].map((frame) => {
            const ordinal = checkpointOrdinal.get(frame);
            if (ordinal === undefined) return null;
            const checkpoint = timeline.checkpoints[ordinal];
            return (
              <line
                key={`flag-${frame}`}
                x1={xPos(ordinal)}
                x2={xPos(ordinal)}
                y1={geometry.plot.y}
                y2={geometry.plot.y + geometry.plot.height}
                stroke="#f59e0b"
                strokeWidth={1}
                strokeDasharray="2 3"
              >
                <title>
                  {`FLAG_TRANSITION at frame ${frame}` +
                    (checkpoint.leader_lap !== null ? `, leader lap ${checkpoint.leader_lap}` : "")}
                </title>
              </line>
            );
          })}

          {alignment && alignment.markerX !== null && (
            <line
              x1={xPos(alignment.markerX)}
              x2={xPos(alignment.markerX)}
              y1={geometry.plot.y}
              y2={geometry.plot.y + geometry.plot.height}
              stroke={alignment.kind === "checkpoint" ? "#e2e8f0" : "#475569"}
              strokeWidth={alignment.kind === "checkpoint" ? 2 : 1}
              strokeDasharray={alignment.kind === "checkpoint" ? undefined : "4 4"}
            >
              <title>
                {alignment.kind === "checkpoint"
                  ? `Current frame is model checkpoint at frame ${frameIndex}`
                  : "Current frame is between model checkpoints"}
              </title>
            </line>
          )}

          {geometry.series.map((series) => {
            const color = colorForDriver(series.driverId);
            return (
              <g key={series.driverId}>
                {series.segments.map((segment, index) =>
                  segment.length === 1 ? (
                    <circle
                      key={`p-${index}`}
                      cx={segment[0].x}
                      cy={segment[0].y}
                      r={2.5}
                      fill={color}
                    />
                  ) : (
                    <polyline
                      key={`s-${index}`}
                      points={segment.map((p) => `${p.x},${p.y}`).join(" ")}
                      fill="none"
                      stroke={color}
                      strokeWidth={1.5}
                    />
                  ),
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
          Driver visibility (display filter only — all {timeline.driver_series.length} series available)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {timeline.driver_series.map((series) => {
            const on = isVisible(series.driver_id);
            return (
              <button
                key={series.driver_id}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  setVisibilityOverrides((prev) => ({
                    ...prev,
                    [series.driver_id]: !on,
                  }))
                }
                className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] ${
                  on
                    ? "border-white/20 bg-white/10 text-slate-100"
                    : "border-white/10 bg-transparent text-slate-500"
                }`}
              >
                <span
                  aria-hidden
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: on ? colorForDriver(series.driver_id) : "#475569" }}
                />
                {series.driver_id}
              </button>
            );
          })}
        </div>
      </div>

      <CheckpointDetails
        timeline={timeline}
        selected={selected}
        alignmentKind={alignment?.kind ?? "none"}
        frameIndex={frameIndex}
        onSelect={setSelectedOverride}
      />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <section aria-label="Win probability evolution" className="flex flex-col gap-3">
      <h2 className="font-heading text-sm font-bold uppercase tracking-[0.16em] text-slate-300">
        Win probability evolution
      </h2>
      {children}
    </section>
  );
}

function CheckpointDetails({
  timeline,
  selected,
  alignmentKind,
  frameIndex,
  onSelect,
}: {
  timeline: ProbabilityTimelineResponse;
  selected: { frame_index: number; state_time_s: number; leader_lap: number | null; reasons: string[] } | null;
  alignmentKind: string;
  frameIndex: number;
  onSelect: (frame: number | null) => void;
}) {
  return (
    <div className="flex flex-col gap-2 border-t border-white/10 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-[11px] uppercase tracking-[0.14em] text-slate-500" htmlFor="checkpoint-select">
          Checkpoint details
        </label>
        <select
          id="checkpoint-select"
          value={selected ? String(selected.frame_index) : ""}
          onChange={(e) => onSelect(e.target.value === "" ? null : Number(e.target.value))}
          className="rounded border border-white/10 bg-slate-900 px-2 py-1 text-xs text-slate-200"
        >
          <option value="">— choose a checkpoint —</option>
          {timeline.checkpoints.map((c) => (
            <option key={c.frame_index} value={c.frame_index}>
              {`frame ${c.frame_index} · ${c.leader_lap !== null ? `L${c.leader_lap}` : "lap n/a"} · ${c.reasons.join("+")}`}
            </option>
          ))}
        </select>
        {alignmentKind === "checkpoint" ? (
          <span className="text-[11px] text-sky-300">current frame is a checkpoint</span>
        ) : (
          <span className="text-[11px] text-slate-500">
            current frame {frameIndex} is between model checkpoints (no current probability)
          </span>
        )}
      </div>

      {selected && (
        <div className="text-xs leading-6 text-slate-300">
          <p className="text-slate-400">
            Frame {selected.frame_index} · T {formatRaceTime(selected.state_time_s)} ·{" "}
            {selected.leader_lap !== null ? `leader lap ${selected.leader_lap}` : "leader lap n/a"} ·{" "}
            reasons: {selected.reasons.join(" + ")}
          </p>
          <table className="mt-1 w-full max-w-xl text-left tabular-nums">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-0.5 pr-3 font-semibold">Driver</th>
                <th className="py-0.5 font-semibold">Winner probability</th>
              </tr>
            </thead>
            <tbody>
              {timeline.driver_series.map((series) => {
                const value = probabilityAtCheckpoint(series, selected.frame_index);
                return (
                  <tr key={series.driver_id} className="border-t border-white/5">
                    <td className="py-0.5 pr-3">{series.driver_id}</td>
                    <td className="py-0.5">
                      {value === null ? "n/a" : `${(value * 100).toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-slate-500">
            Factual aggregate of listed estimates:{" "}
            {(sumProbabilities(
              timeline.driver_series.map((s) => probabilityAtCheckpoint(s, selected.frame_index)),
            ) * 100).toFixed(2)}
            % — independent binary estimates, not shares.
          </p>
        </div>
      )}
    </div>
  );
}
