// P12-5 spatial API client + renderer view-model (Phase-12 P12-6).
//
// Typed boundary over the spatial routes. The frontend deals only in the
// public DTOs (geometry, frame, causal window) — it never recreates
// geometry, normalization, availability math, or temporal resolution.
// Backend contracts are authoritative; this module only maps them into
// deterministic SVG view-model data.
//
// No `any` in spatial contracts. fetch is injectable for tests. All
// mapping helpers are pure and side-effect free so `node --test` covers
// them without a DOM.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { API_BASE, readJson as readSharedJson, resolveBase as sharedResolveBase, type FetchLike as SharedFetchLike } from "./http.ts";

export const SPATIAL_API_BASE = API_BASE;

// Square viewBox convention: svg = render * SPATIAL_VIEWBOX. The backend
// supplies normalized y-down [0, 1] coordinates; this factor is
// PRESENTATIONAL ONLY and never alters spatial relationships.
export const SPATIAL_VIEWBOX = 1000;

export const PIT_GEOMETRY_SUPPORTED = "PIT_GEOMETRY_SUPPORTED";
export const SPATIAL_SOURCE_PARTIAL = "PARTIAL";

// --- P12-5 public contract types (mirror api/v2_spatial_schemas.py) ---

export type RenderPoint = [number, number];

export type SpatialTrack = {
  points: RenderPoint[];
  n_points: number;
  closed_loop: boolean;
};

export type SpatialGeometry = {
  race_id: string;
  schema_version: string;
  algorithm_version: string;
  geometry_sha256: string;
  main_track: SpatialTrack;
  pit_lane: SpatialTrack | null;
  pit_status: string;
  render_bounds: Record<string, number>;
};

export type SpatialAvailability = "FRESH" | "STALE" | "UNAVAILABLE";

export type SpatialDriverState = {
  driver_id: string | null;
  driver_number: number | null;
  availability: SpatialAvailability;
  observation_time_s: number | null;
  age_s: number | null;
  render_x: number | null;
  render_y: number | null;
  outside_viewport: boolean;
};

export type SpatialFrame = {
  race_id: string;
  frame_index: number;
  query_time_s: number;
  source_status: string;
  geometry_sha256: string | null;
  observation_content_sha256: string;
  resolver_contract_version: string;
  fresh_count: number;
  stale_count: number;
  unavailable_count: number;
  drivers: SpatialDriverState[];
};

export type SpatialWindowSample = {
  observation_time_s: number;
  render_x: number | null;
  render_y: number | null;
};

export type SpatialWindow = {
  race_id: string;
  frame_index: number;
  driver_number: number;
  query_time_s: number;
  history_s: number;
  sample_count: number;
  samples: SpatialWindowSample[];
};

// --- transport ---

export type SpatialFetchLike = SharedFetchLike;

export type SpatialErrorBody = {
  error?: string;
  detail?: string;
};

export class SpatialApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, body: SpatialErrorBody | null) {
    super(
      `Spatial API ${status}${body?.error ? `: ${body.error}` : ""}` +
        (body?.detail ? ` — ${body.detail}` : ""),
    );
    this.name = "SpatialApiError";
    this.status = status;
    this.code = body?.error ?? null;
  }

  isUnavailable(): boolean {
    return this.status === 404 && this.code === "spatial_unavailable";
  }

  isUnknownRace(): boolean {
    return this.status === 404 && this.code === "unknown_race";
  }

  isIntegrityError(): boolean {
    return this.status === 500 && this.code === "spatial_integrity_error";
  }
}

async function readSpatialJson<T>(
  fetcher: SpatialFetchLike,
  url: string,
  init?: RequestInit,
): Promise<T> {
  return readSharedJson<T>(
    fetcher,
    url,
    init,
    (status, body) => new SpatialApiError(status, body as SpatialErrorBody),
  );
}

const spatialBaseOf = (base?: string): string => sharedResolveBase(base);

function spatialRacePath(raceId: string): string {
  return `${encodeURIComponent(raceId)}/spatial`;
}

export async function getSpatialGeometry(
  raceId: string,
  fetcher: SpatialFetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<SpatialGeometry> {
  const url = `${spatialBaseOf(base)}/v2/races/${spatialRacePath(raceId)}/geometry`;
  return readSpatialJson<SpatialGeometry>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

export async function getSpatialFrame(
  raceId: string,
  frameIndex: number,
  fetcher: SpatialFetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<SpatialFrame> {
  const url =
    `${spatialBaseOf(base)}/v2/races/${spatialRacePath(raceId)}` +
    `/frame/${frameIndex}`;
  return readSpatialJson<SpatialFrame>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

export async function getSpatialWindow(
  raceId: string,
  frameIndex: number,
  driverNumber: number,
  historyS: number,
  fetcher: SpatialFetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<SpatialWindow> {
  const url =
    `${spatialBaseOf(base)}/v2/races/${spatialRacePath(raceId)}` +
    `/window/${frameIndex}?driver_number=${driverNumber}&history_s=${historyS}`;
  return readSpatialJson<SpatialWindow>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

// --- pure SVG view-model (deterministic, no DOM) ---

/** Backend render unit -> SVG user unit. Exact: 0.25 -> 250. */
export function toSvgX(renderX: number): number {
  return renderX * SPATIAL_VIEWBOX;
}

/** Backend render unit -> SVG user unit. Exact: 0.75 -> 750. */
export function toSvgY(renderY: number): number {
  return renderY * SPATIAL_VIEWBOX;
}

/** Deterministic coordinate quantizer (millis SVG units, no drift). */
export function formatSvgCoord(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/**
 * Deterministic path `d` for a supplied point array (already in render
 * space). Closed loops get `Z`; nothing is smoothed, resampled, or
 * reordered — the backend polyline is truth.
 */
export function trackPath(points: RenderPoint[], closed: boolean): string {
  const head = points
    .map(
      ([x, y], i) =>
        `${i === 0 ? "M" : "L"}${formatSvgCoord(toSvgX(x))} ${formatSvgCoord(toSvgY(y))}`,
    )
    .join(" ");
  return closed ? `${head} Z` : head;
}

/** Open deterministic path through already-known trail samples. */
export function trailPath(samples: SpatialWindowSample[]): string {
  const pts: RenderPoint[] = [];
  for (const s of samples) {
    if (Number.isFinite(s.render_x) && Number.isFinite(s.render_y)) {
      pts.push([s.render_x as number, s.render_y as number]);
    }
  }
  return trackPath(pts, false);
}

export type MarkerDatum = {
  key: string;
  driverId: string | null;
  driverNumber: number | null;
  label: string;
  availability: SpatialAvailability;
  cx: number;
  cy: number;
  outsideViewport: boolean;
  ageS: number | null;
};

/** Compact track label: number when present, else driver id. */
export function markerLabel(driver: SpatialDriverState): string {
  if (driver.driver_number !== null && driver.driver_number !== undefined) {
    return String(driver.driver_number);
  }
  return driver.driver_id ?? "—";
}

function isPlottable(driver: SpatialDriverState): boolean {
  return (
    (driver.availability === "FRESH" || driver.availability === "STALE") &&
    Number.isFinite(driver.render_x) &&
    Number.isFinite(driver.render_y)
  );
}

/**
 * One datum per driver with usable coordinates, in frame order.
 * UNAVAILABLE drivers (and null-coordinate rows) yield no datum — the
 * renderer draws no fake marker. Positions are exact backend values;
 * labels never move the marker.
 */
export function markerData(frame: SpatialFrame): MarkerDatum[] {
  return frame.drivers.filter(isPlottable).map((driver, i) => ({
    key: `${driver.driver_id ?? "number"}:${driver.driver_number ?? i}`,
    driverId: driver.driver_id,
    driverNumber: driver.driver_number,
    label: markerLabel(driver),
    availability: driver.availability,
    cx: toSvgX(driver.render_x as number),
    cy: toSvgY(driver.render_y as number),
    outsideViewport: driver.outside_viewport,
    ageS: driver.age_s,
  }));
}

/** Frame markers must sit on the geometry they were resolved against. */
export function geometryMatchesFrame(
  geometry: SpatialGeometry,
  frame: SpatialFrame,
): boolean {
  return (
    geometry.race_id === frame.race_id &&
    frame.geometry_sha256 !== null &&
    geometry.geometry_sha256 === frame.geometry_sha256
  );
}

export function isPartialFrame(frame: SpatialFrame): boolean {
  return frame.source_status === SPATIAL_SOURCE_PARTIAL;
}

/** Drivers in the frame universe with no spatial marker. */
export function unplottedDrivers(frame: SpatialFrame): SpatialDriverState[] {
  return frame.drivers.filter((d) => !isPlottable(d));
}
