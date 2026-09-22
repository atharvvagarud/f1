// Win-probability evolution chart (Phase-5 R6; UI3 technical chart).
//
// SVG only (no chart dependency: package.json audited). Renders ACTUAL model
// checkpoints only; lines visually connect consecutive observations for the
// same driver and break at null (never plotted as 0). No stacked/share/pie
// view: INDEPENDENT_BINARY values are not a mutually exclusive distribution.
// The current replay frame is marked separately; between checkpoints no current
// probability is implied. Series differ by dash pattern as well as hue, and the
// legend prints driver ids, so nothing is encoded by colour alone. Flat grid,
// no gradients, no decorative fill.

"use client";

import { useMemo, useState } from "react";
import type { ProbabilityTimelineResponse } from "@/lib/v2";
import type { ProbabilityTimelineView } from "@/features/replay/hooks/useReplay";
import {
  buildChartGeometry,
  chartHeightForWidth,
  checkpointAt,
  currentFrameAlignment,
  defaultVisibleDrivers,
  probabilityAtCheckpoint,
  seriesDashPattern,
} from "@/features/replay/lib/probabilityTimeline";
import {
  formatRaceTime,
  sumProbabilities,
} from "@/features/replay/lib/replayMachine";
import { useElementWidth } from "@/features/replay/hooks/useElementWidth";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";

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

const GRID = "#1c2530"; // ink-700
const RULE = "#2b3644"; // ink-600
const TICK = "#74828f"; // fg-dim
const WARN = "#d29922"; // warn
const FG = "#e7ecf3"; // fg

function unavailableState(reason: string | null) {
  return (
    <div role="status" className="border border-warn/40 bg-ink-950 px-3 py-2.5">
      <p className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-warn">
        Cache not available
      </p>
      <p className="mt-1 font-data text-[11px] leading-5 text-fg-muted">
        Historical prediction cache has not been generated for this race
        {reason ? ` (${reason})` : ""}. No current probability is implied and
        factual replay is unaffected.
      </p>
    </div>
  );
}

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
  const [chartRef, chartWidth] = useElementWidth<HTMLDivElement>(560);
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
        <p
          role="status"
          className="border border-ink-700 bg-ink-950 px-3 py-2.5 font-data text-[11px] text-fg-muted"
        >
          Loading probability timeline…
        </p>
      </Shell>
    );
  }

  if (view.kind === "unavailable") {
    return <Shell>{unavailableState(view.reason)}</Shell>;
  }

  if (view.kind === "error") {
    return (
      <Shell>
        <div
          role="alert"
          className="border border-danger/40 bg-ink-950 px-3 py-2.5 font-data text-[11px] leading-5 text-fg"
        >
          {view.message}
        </div>
      </Shell>
    );
  }

  if (!timeline) return null;

  const visibleDrivers = timeline.driver_series
    .map((s) => s.driver_id)
    .filter(isVisible);
  const visibleIndex = new Map(visibleDrivers.map((id, i) => [id, i]));
  const chartHeight = chartHeightForWidth(chartWidth);
  const geometry = buildChartGeometry(timeline, visibleDrivers, {
    width: Math.max(chartWidth, 240),
    height: chartHeight,
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

  const chartDescription =
    `Win probability evolution across ${timeline.checkpoints.length} recorded ` +
    `model checkpoints for ${timeline.driver_series.length} drivers. Each line ` +
    `is an independent binary estimate shown verbatim, not a share; lines break ` +
    `at unevaluated checkpoints.`;

  return (
    <Shell>
      <SemanticsNote>
        {timeline.probability_semantics} — each line is an independent binary
        estimate; values are shown verbatim and are not shares (their sum need
        not be 100%). Points exist only where the frozen model was evaluated.
      </SemanticsNote>

      <div ref={chartRef} className="w-full min-w-0 overflow-hidden">
        <svg
          role="img"
          aria-label={chartDescription}
          width={geometry.width}
          height={geometry.height}
          viewBox={`0 0 ${geometry.width} ${geometry.height}`}
          className="block w-full"
        >
          <title>{chartDescription}</title>

          {geometry.yTicks.map((tick) => (
            <g key={`y-${tick.value}`}>
              <line
                x1={geometry.plot.x}
                x2={geometry.plot.x + geometry.plot.width}
                y1={tick.y}
                y2={tick.y}
                stroke={GRID}
                strokeWidth={1}
              />
              <text x={4} y={tick.y + 3} fill={TICK} fontSize={10}>
                {tick.label}
              </text>
            </g>
          ))}
          {geometry.xTicks.map((tick) => (
            <text
              key={`x-${tick.frameIndex}`}
              x={tick.x}
              y={geometry.height - 8}
              fill={TICK}
              fontSize={10}
              textAnchor="middle"
            >
              {tick.label}
            </text>
          ))}

          <line
            x1={geometry.plot.x}
            x2={geometry.plot.x + geometry.plot.width}
            y1={geometry.plot.y + geometry.plot.height}
            y2={geometry.plot.y + geometry.plot.height}
            stroke={RULE}
            strokeWidth={1}
          />

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
                stroke={WARN}
                strokeWidth={1}
                strokeDasharray="2 3"
              >
                <title>
                  {`FLAG_TRANSITION at frame ${frame}` +
                    (checkpoint.leader_lap !== null
                      ? `, leader lap ${checkpoint.leader_lap}`
                      : "")}
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
              stroke={alignment.kind === "checkpoint" ? FG : RULE}
              strokeWidth={alignment.kind === "checkpoint" ? 2 : 1}
              strokeDasharray={
                alignment.kind === "checkpoint" ? undefined : "4 4"
              }
            >
              <title>
                {alignment.kind === "checkpoint"
                  ? `Current frame is a model checkpoint at frame ${frameIndex}`
                  : "Current frame is between model checkpoints"}
              </title>
            </line>
          )}

          {geometry.series.map((series) => {
            const color = colorForDriver(series.driverId);
            const dash = seriesDashPattern(
              visibleIndex.get(series.driverId) ?? 0,
            );
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
                      strokeDasharray={dash}
                    />
                  ),
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-col gap-2">
        <p className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
          Driver visibility (display filter only — all{" "}
          {timeline.driver_series.length} series available)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {timeline.driver_series.map((series) => {
            const on = isVisible(series.driver_id);
            const dashIndex = visibleIndex.get(series.driver_id) ?? 0;
            const dash = seriesDashPattern(dashIndex);
            const color = on ? colorForDriver(series.driver_id) : TICK;
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
                className={`flex items-center gap-1.5 rounded-chip border px-2 py-0.5 font-ui text-[10px] uppercase tracking-[0.08em] focus-visible:outline-2 focus-visible:outline-focus ${
                  on
                    ? "border-ink-600 bg-ink-850 text-fg"
                    : "border-ink-700 bg-transparent text-fg-dim"
                }`}
              >
                <svg aria-hidden="true" width={16} height={8} viewBox="0 0 16 8">
                  <line
                    x1={0}
                    x2={16}
                    y1={4}
                    y2={4}
                    stroke={color}
                    strokeWidth={2}
                    strokeDasharray={on ? dash : "1 2"}
                  />
                </svg>
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
    <Panel>
      <PanelHeader title="Win probability evolution" />
      <div className="flex flex-col gap-3 px-4 py-3">{children}</div>
    </Panel>
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
  selected: {
    frame_index: number;
    state_time_s: number;
    leader_lap: number | null;
    reasons: string[];
  } | null;
  alignmentKind: string;
  frameIndex: number;
  onSelect: (frame: number | null) => void;
}) {
  return (
    <div className="flex flex-col gap-2 border-t border-ink-700 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <label
          className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim"
          htmlFor="checkpoint-select"
        >
          Checkpoint details
        </label>
        <select
          id="checkpoint-select"
          value={selected ? String(selected.frame_index) : ""}
          onChange={(e) =>
            onSelect(e.target.value === "" ? null : Number(e.target.value))
          }
          className="h-8 border border-ink-700 bg-ink-950 px-2 font-data text-[11px] text-fg focus-visible:border-ink-600"
        >
          <option value="">— choose a checkpoint —</option>
          {timeline.checkpoints.map((c) => (
            <option key={c.frame_index} value={c.frame_index}>
              {`frame ${c.frame_index} · ${
                c.leader_lap !== null ? `L${c.leader_lap}` : "lap n/a"
              } · ${c.reasons.join("+")}`}
            </option>
          ))}
        </select>
        {alignmentKind === "checkpoint" ? (
          <span className="font-data text-[11px] text-info">
            current frame is a checkpoint
          </span>
        ) : (
          <span className="font-data text-[11px] text-fg-dim">
            current frame {frameIndex} is between model checkpoints (no current
            probability)
          </span>
        )}
      </div>

      {selected && (
        <div className="font-data text-[11px] leading-5 text-fg-muted">
          <p>
            Frame {selected.frame_index} · T{" "}
            {formatRaceTime(selected.state_time_s)} ·{" "}
            {selected.leader_lap !== null
              ? `leader lap ${selected.leader_lap}`
              : "leader lap n/a"}{" "}
            · reasons: {selected.reasons.join(" + ")}
          </p>
          <table className="mt-1 w-full max-w-xl text-left tabular-nums">
            <thead>
              <tr className="font-ui text-[10px] uppercase tracking-[0.1em] text-fg-dim">
                <th className="py-0.5 pr-3 font-semibold">Driver</th>
                <th className="py-0.5 font-semibold">Winner probability</th>
              </tr>
            </thead>
            <tbody>
              {timeline.driver_series.map((series) => {
                const value = probabilityAtCheckpoint(
                  series,
                  selected.frame_index,
                );
                return (
                  <tr key={series.driver_id} className="border-t border-ink-700">
                    <td className="py-0.5 pr-3">{series.driver_id}</td>
                    <td className="py-0.5">
                      {value === null ? "n/a" : `${(value * 100).toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-fg-dim">
            Factual aggregate of listed estimates:{" "}
            {(
              sumProbabilities(
                timeline.driver_series.map((s) =>
                  probabilityAtCheckpoint(s, selected.frame_index),
                ),
              ) * 100
            ).toFixed(2)}
            % — independent binary estimates, not shares.
          </p>
        </div>
      )}
    </div>
  );
}
