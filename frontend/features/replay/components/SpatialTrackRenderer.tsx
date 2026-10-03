// SVG track renderer (Phase-12 P12-6; brutalist telemetry panel).
//
// THE FRONTEND RENDERS TRUTH. Geometry, driver coordinates, and
// availability arrive resolved from P12-5; this component maps them
// into SVG deterministically and nothing else: no geometry rebuild, no
// normalization, no snapping, no smoothing, no future-aware motion.
// Marker dots sit exactly on render_x/render_y; only paint order and
// label placement adapt (labels never move the dot).
//
// Coordinate convention: viewBox "0 0 1000 1000",
// svg = render * 1000 (see lib/spatial.ts). Aspect is preserved with
// xMidYMid meet, so the circuit is geometrically identical at any
// panel width. Strokes use non-scaling-stroke to stay legible.

"use client";

import { useMemo } from "react";

import { Panel, PanelHeader } from "@/components/ui/Panel";
import {
  SPATIAL_VIEWBOX,
  PIT_GEOMETRY_SUPPORTED,
  geometryMatchesFrame,
  isPartialFrame,
  markerData,
  trackPath,
  trailPath,
  unplottedDrivers,
  type MarkerDatum,
  type SpatialFrame,
  type SpatialGeometry,
  type SpatialWindowSample,
} from "@/lib/spatial";

export type SpatialRendererStatus =
  | "loading"
  | "ready"
  | "error"
  | "unavailable";

const TRACK_BED_WIDTH = 9;
const TRACK_LINE_WIDTH = 2.5;
const PIT_WIDTH = 2;
const MARKER_R = 7;
const MARKER_SELECTED_R = 9;

function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 8) : "—";
}

function formatAge(ageS: number | null): string {
  if (ageS === null || ageS === undefined || !Number.isFinite(ageS)) return "—";
  return `${ageS.toFixed(1)} s`;
}

function markerTitle(datum: MarkerDatum): string {
  const who =
    datum.driverId !== null && datum.driverNumber !== null
      ? `${datum.driverId} #${datum.driverNumber}`
      : (datum.driverId ?? `#${datum.driverNumber ?? datum.label}`);
  return `${who} — ${datum.availability}, age ${formatAge(datum.ageS)}`;
}

function DriverMarker({
  datum,
  selected,
}: {
  datum: MarkerDatum;
  selected: boolean;
}) {
  const stale = datum.availability === "STALE";
  return (
    <g>
      <title>{markerTitle(datum)}</title>
      <circle
        cx={datum.cx}
        cy={datum.cy}
        r={selected ? MARKER_SELECTED_R : MARKER_R}
        vectorEffect="non-scaling-stroke"
        className={
          stale
            ? "fill-ink-950 stroke-fg-dim opacity-80 [stroke-dasharray:3_2]"
            : "fill-fg stroke-ink-950"
        }
        strokeWidth={selected ? 3 : 2}
        style={selected ? { stroke: "var(--color-signal)" } : undefined}
      />
      <text
        x={datum.cx + (selected ? MARKER_SELECTED_R : MARKER_R) + 5}
        y={datum.cy + 4.5}
        className={`font-data ${stale ? "fill-fg-dim" : "fill-fg-muted"}`}
        fontSize={13}
        textAnchor="start"
        aria-hidden="true"
      >
        {datum.label}
      </text>
    </g>
  );
}

/** Pure presentation primitive for already-supplied causal trail samples. */
export function DriverTrail({
  samples,
}: {
  samples: SpatialWindowSample[];
}) {
  const d = trailPath(samples);
  if (!d) return null;
  return (
    <path
      d={d}
      fill="none"
      vectorEffect="non-scaling-stroke"
      className="stroke-fg-dim opacity-60"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    />
  );
}

function StateBlock({
  tone,
  title,
  body,
}: {
  tone: "loading" | "error" | "empty";
  title: string;
  body: string;
}) {
  const border =
    tone === "error" ? "border-danger/40" : "border-ink-700";
  return (
    <div
      role={tone === "loading" ? "status" : "alert"}
      className={`border ${border} bg-ink-900 px-4 py-6`}
    >
      <p className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
        {title}
      </p>
      <p className="mt-2 font-data text-[12px] leading-6 text-fg-muted">
        {body}
      </p>
    </div>
  );
}

export function SpatialTrackRenderer({
  geometry,
  frame,
  status,
  errorDetail,
  selectedDriverId = null,
  trail = null,
  headline,
}: {
  geometry: SpatialGeometry | null;
  frame: SpatialFrame | null;
  status: SpatialRendererStatus;
  errorDetail?: string | null;
  selectedDriverId?: string | null;
  trail?: SpatialWindowSample[] | null;
  headline?: string;
}) {
  const markers = useMemo(
    () => (status === "ready" && frame ? markerData(frame) : []),
    [status, frame],
  );
  const ordered = useMemo(() => {
    if (selectedDriverId === null) return markers;
    // Paint order only: the selected marker renders last (on top).
    // Coordinates are never touched.
    return [
      ...markers.filter((m) => m.driverId !== selectedDriverId),
      ...markers.filter((m) => m.driverId === selectedDriverId),
    ];
  }, [markers, selectedDriverId]);

  const mainD = geometry ? trackPath(geometry.main_track.points, true) : "";
  const pitD =
    geometry?.pit_lane && geometry.pit_status === PIT_GEOMETRY_SUPPORTED
      ? trackPath(geometry.pit_lane.points, false)
      : null;
  const integrityOk =
    status === "ready" && geometry !== null && frame !== null
      ? geometryMatchesFrame(geometry, frame)
      : false;
  const partial = status === "ready" && frame ? isPartialFrame(frame) : false;
  const unplotted =
    status === "ready" && frame ? unplottedDrivers(frame).length : 0;
  const offMap = markers.filter((m) => m.outsideViewport).length;

  const headerMeta =
    status === "ready" && frame
      ? [
          `T ${frame.query_time_s.toFixed(3)} S`,
          `${frame.drivers.length} DRIVERS`,
          `${frame.fresh_count} FRESH`,
          frame.stale_count > 0 ? `${frame.stale_count} STALE` : null,
          unplotted > 0 ? `${unplotted} NO FIX` : null,
          partial ? "PARTIAL COVERAGE" : null,
          `GEO ${shortHash(frame.geometry_sha256)}`,
        ]
          .filter((part): part is string => part !== null)
          .join(" · ")
      : undefined;

  if (status === "loading") {
    return (
      <StateBlock
        tone="loading"
        title="Track data / loading"
        body="Loading circuit geometry and spatial frame…"
      />
    );
  }
  if (status === "unavailable") {
    return (
      <StateBlock
        tone="empty"
        title="Spatial data unavailable"
        body="No servable spatial state for this race. Replay itself remains usable."
      />
    );
  }
  if (status === "error" || geometry === null || frame === null) {
    return (
      <StateBlock
        tone="error"
        title="Track data / error"
        body={errorDetail ?? "Spatial request failed. No fallback geometry is rendered."}
      />
    );
  }
  if (!integrityOk) {
    return (
      <StateBlock
        tone="error"
        title="Track data / integrity"
        body="Frame geometry identity does not match the circuit geometry. Markers withheld."
      />
    );
  }

  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        title={headline ?? "Track map"}
        meta={headerMeta}
        note={
          partial
            ? "PARTIAL SPATIAL COVERAGE — drivers without a fix carry no marker."
            : undefined
        }
      />
      <div className="overflow-hidden bg-ink-950">
        <svg
          viewBox={`0 0 ${SPATIAL_VIEWBOX} ${SPATIAL_VIEWBOX}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={`Circuit map for ${geometry.race_id}, frame ${frame.frame_index}: ${markers.length} positioned drivers, ${unplotted} without a fix.`}
          className="block h-auto w-full"
        >
          <title>
            {`Circuit ${geometry.race_id} frame ${frame.frame_index}`}
          </title>
          {/* Track bed (subordinate) + racing line (high contrast). */}
          <path
            d={mainD}
            fill="none"
            vectorEffect="non-scaling-stroke"
            className="stroke-ink-600"
            strokeWidth={TRACK_BED_WIDTH}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          />
          <path
            d={mainD}
            fill="none"
            vectorEffect="non-scaling-stroke"
            className="stroke-fg"
            strokeWidth={TRACK_LINE_WIDTH}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          />
          {pitD ? (
            <path
              d={pitD}
              fill="none"
              vectorEffect="non-scaling-stroke"
              className="stroke-fg-dim"
              strokeWidth={PIT_WIDTH}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            />
          ) : null}
          {trail ? <DriverTrail samples={trail} /> : null}
          {ordered.map((datum) => (
            <DriverMarker
              key={datum.key}
              datum={datum}
              selected={datum.driverId === selectedDriverId}
            />
          ))}
        </svg>
      </div>
      <div className="flex flex-wrap gap-x-4 border-t border-ink-700 px-4 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
        <span>
          T {frame.query_time_s.toFixed(3)} S · FRAME {frame.frame_index}
        </span>
        <span>SRC {frame.source_status}</span>
        {offMap > 0 ? <span>{offMap} OFF MAP</span> : null}
        <span>GEO {shortHash(geometry.geometry_sha256)}</span>
      </div>
    </Panel>
  );
}
