// Synthetic harness fixtures (Phase-12 P12-6 validation only).
//
// Compact geometric loops — NOT circuit data, NOT backend geometry.
// They exercise renderer layout (closed loop, pit branch, availability
// mix, PARTIAL, selection) without the backend corpus. Real circuits
// are validated in live mode against P12-5.

import type {
  RenderPoint,
  SpatialDriverState,
  SpatialFrame,
  SpatialGeometry,
} from "@/lib/spatial";

function loopPoints(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  n: number,
): RenderPoint[] {
  const pts: RenderPoint[] = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2;
    pts.push([cx + rx * Math.cos(t), cy + ry * Math.sin(t)]);
  }
  return pts;
}

function fixtureGeometry(
  raceId: string,
  withPit: boolean,
): SpatialGeometry {
  return {
    race_id: raceId,
    schema_version: "spatial-geometry-v1",
    algorithm_version: "p12-3-v1",
    geometry_sha256: `fixture-${raceId}`,
    main_track: {
      points: loopPoints(0.5, 0.5, 0.42, 0.34, 48),
      n_points: 48,
      closed_loop: true,
    },
    pit_lane: withPit
      ? {
          points: loopPoints(0.5, 0.78, 0.3, 0.05, 16),
          n_points: 16,
          closed_loop: false,
        }
      : null,
    pit_status: withPit
      ? "PIT_GEOMETRY_SUPPORTED"
      : "PIT_GEOMETRY_DEFERRED",
    render_bounds: { u_min: 0, v_min: 0, u_max: 1, v_max: 1 },
  };
}

function fixtureDriver(
  driverId: string,
  driverNumber: number | null,
  availability: SpatialDriverState["availability"],
  render: RenderPoint | null,
  ageS: number | null,
): SpatialDriverState {
  const outside = render
    ? render[0] < 0 || render[0] > 1 || render[1] < 0 || render[1] > 1
    : false;
  return {
    driver_id: driverId,
    driver_number: driverNumber,
    availability,
    observation_time_s: render ? 100.0 : null,
    age_s: ageS,
    render_x: render ? render[0] : null,
    render_y: render ? render[1] : null,
    outside_viewport: outside,
  };
}

function fixtureFrame(
  raceId: string,
  drivers: SpatialDriverState[],
  sourceStatus: string,
): SpatialFrame {
  return {
    race_id: raceId,
    frame_index: 42,
    query_time_s: 100.0,
    source_status: sourceStatus,
    geometry_sha256: `fixture-${raceId}`,
    observation_content_sha256: "fixture-obs",
    resolver_contract_version: "spatial-resolver-v1",
    fresh_count: drivers.filter((d) => d.availability === "FRESH").length,
    stale_count: drivers.filter((d) => d.availability === "STALE").length,
    unavailable_count: drivers.filter(
      (d) => d.availability === "UNAVAILABLE",
    ).length,
    drivers,
  };
}

export type FixtureCase = {
  id: string;
  label: string;
  geometry: SpatialGeometry;
  frame: SpatialFrame;
  selectedDriverId: string | null;
};

const PACK: SpatialDriverState[] = [
  fixtureDriver("verstappen", 1, "FRESH", [0.5, 0.16], 0.2),
  fixtureDriver("hamilton", 44, "FRESH", [0.52, 0.17], 0.4),
  fixtureDriver("leclerc", 16, "STALE", [0.2, 0.6], 12.0),
  fixtureDriver("norris", 4, "FRESH", [0.85, 0.45], 0.1),
  fixtureDriver("piastri", 81, "FRESH", [1.12, 0.5], 0.3),
  fixtureDriver("sainz", 55, "UNAVAILABLE", null, null),
  fixtureDriver("rookie", null, "UNAVAILABLE", null, null),
];

export const FIXTURES: FixtureCase[] = [
  {
    id: "pack",
    label: "Marker pack (synthetic loop + pit)",
    geometry: fixtureGeometry("fixture-pack", true),
    frame: fixtureFrame("fixture-pack", PACK, "COMPLETE"),
    selectedDriverId: "verstappen",
  },
  {
    id: "nopit",
    label: "Pit deferred (no fabricated lane)",
    geometry: fixtureGeometry("fixture-nopit", false),
    frame: fixtureFrame("fixture-nopit", PACK, "COMPLETE"),
    selectedDriverId: null,
  },
  {
    id: "partial",
    label: "PARTIAL coverage",
    geometry: fixtureGeometry("fixture-partial", true),
    frame: fixtureFrame("fixture-partial", PACK, "PARTIAL"),
    selectedDriverId: null,
  },
];
