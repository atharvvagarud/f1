import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extensions: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppressions below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { canRenderSpatialFrame, classifySpatialFailure, createSpatialRequestTracker, isSpatialClockConsistent, isSpatialResponseCurrent, spatialFrameCacheKey, spatialSelectionForRace } from "./spatialIntegration.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { SpatialApiError, geometryMatchesFrame, isPartialFrame, markerData, type SpatialFrame, type SpatialGeometry } from "../../../lib/spatial.ts";

// Contract tests for the P12-7 replay-integration guards: the exact
// predicates the track panel runs (request identity, out-of-order
// protection, race-switch safety, clock agreement, failure routing).
// Run with `node --test features/replay/lib/spatialIntegration.test.ts`.

function geometry(over: Partial<SpatialGeometry> = {}): SpatialGeometry {
  return {
    race_id: "2023-r01-R",
    schema_version: "spatial-geometry-v1",
    algorithm_version: "p12-3-v1",
    geometry_sha256: "g".repeat(64),
    main_track: {
      points: [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ],
      n_points: 4,
      closed_loop: true,
    },
    pit_lane: null,
    pit_status: "PIT_GEOMETRY_DEFERRED",
    render_bounds: { u_min: 0, v_min: 0, u_max: 1, v_max: 1 },
    ...over,
  };
}

function frame(over: Partial<SpatialFrame> = {}): SpatialFrame {
  return {
    race_id: "2023-r01-R",
    frame_index: 10,
    query_time_s: 1234.567,
    source_status: "FULL",
    geometry_sha256: "g".repeat(64),
    observation_content_sha256: "o".repeat(64),
    resolver_contract_version: "p12-4-v1",
    fresh_count: 1,
    stale_count: 0,
    unavailable_count: 0,
    drivers: [
      {
        driver_id: "hamilton",
        driver_number: 44,
        availability: "FRESH",
        observation_time_s: 1234.567,
        age_s: 0.0,
        render_x: 0.25,
        render_y: 0.75,
        outside_viewport: false,
      },
    ],
    ...over,
  };
}

describe("frame cache identity", () => {
  it("keys cache by race AND frame, never frame alone", () => {
    assert.equal(spatialFrameCacheKey("2023-r01-R", 10), "2023-r01-R|10");
    assert.notEqual(
      spatialFrameCacheKey("2023-r01-R", 10),
      spatialFrameCacheKey("2021-r05-R", 10),
    );
    assert.notEqual(
      spatialFrameCacheKey("2023-r01-R", 10),
      spatialFrameCacheKey("2023-r01-R", 11),
    );
  });
});

describe("response identity", () => {
  it("accepts only the exact requested race and frame index", () => {
    const f = frame();
    assert.equal(isSpatialResponseCurrent(f, "2023-r01-R", 10), true);
    assert.equal(isSpatialResponseCurrent(f, "2023-r01-R", 11), false);
    assert.equal(isSpatialResponseCurrent(f, "2021-r05-R", 10), false);
  });

  it("covers first and last frames identically", () => {
    assert.equal(isSpatialResponseCurrent(frame({ frame_index: 0 }), "2023-r01-R", 0), true);
    assert.equal(
      isSpatialResponseCurrent(frame({ frame_index: 1090 }), "2023-r01-R", 1090),
      true,
    );
    assert.equal(
      isSpatialResponseCurrent(frame({ frame_index: 1090 }), "2023-r01-R", 1089),
      false,
    );
  });
});

describe("out-of-order protection (P12-7 gate)", () => {
  it("request 10, 11, 12 resolving as 12, 10, 11 renders 12", () => {
    const tracker = createSpatialRequestTracker();
    const t10 = tracker.issue("2023-r01-R", 10);
    const t11 = tracker.issue("2023-r01-R", 11);
    const t12 = tracker.issue("2023-r01-R", 12);
    // Resolutions arrive 12, 10, 11: only 12 is ever current.
    assert.equal(tracker.isCurrent(t12), true);
    assert.equal(tracker.isCurrent(t10), false);
    assert.equal(tracker.isCurrent(t11), false);
    assert.equal(tracker.isCurrent(t12), true);
  });

  it("rapid next/previous churn keeps only the latest ticket", () => {
    const tracker = createSpatialRequestTracker();
    const tickets = [
      tracker.issue("2023-r01-R", 100),
      tracker.issue("2023-r01-R", 101),
      tracker.issue("2023-r01-R", 100),
      tracker.issue("2023-r01-R", 102),
    ];
    const last = tickets[tickets.length - 1];
    for (const t of tickets.slice(0, -1)) assert.equal(tracker.isCurrent(t), false);
    assert.equal(tracker.isCurrent(last), true);
  });

  it("late previous-race response is discarded on race switch", () => {
    const tracker = createSpatialRequestTracker();
    const raceA = tracker.issue("2023-r01-R", 55);
    assert.equal(tracker.isCurrent(raceA), true);
    const raceB = tracker.issue("2021-r05-R", 3);
    // Race A resolves late: no longer current, never renders on race B.
    assert.equal(tracker.isCurrent(raceA), false);
    assert.equal(tracker.isCurrent(raceB), true);
    assert.equal(isSpatialResponseCurrent(frame(), "2021-r05-R", 3), false);
  });
});

describe("clock agreement", () => {
  it("requires exact query_time_s equality, no rounding of T", () => {
    const f = frame({ query_time_s: 1234.567 });
    assert.equal(isSpatialClockConsistent(1234.567, f), true);
    assert.equal(isSpatialClockConsistent(1234.5671, f), false);
    assert.equal(isSpatialClockConsistent(1235, f), false);
  });

  it("rejects non-finite replay clocks", () => {
    assert.equal(isSpatialClockConsistent(Number.NaN, frame()), false);
  });
});

describe("render gate", () => {
  it("renders when identity, clock, and geometry all agree", () => {
    assert.equal(
      canRenderSpatialFrame(geometry(), frame(), "2023-r01-R", 10, 1234.567),
      true,
    );
  });

  it("withholds on stale frame, wrong race, clock drift, geometry mismatch", () => {
    const g = geometry();
    const f = frame();
    assert.equal(canRenderSpatialFrame(g, frame({ frame_index: 9 }), "2023-r01-R", 10, 1234.567), false);
    assert.equal(canRenderSpatialFrame(g, frame({ race_id: "2021-r05-R" }), "2023-r01-R", 10, 1234.567), false);
    assert.equal(canRenderSpatialFrame(g, f, "2023-r01-R", 10, 9999.0), false);
    assert.equal(
      canRenderSpatialFrame(
        geometry({ geometry_sha256: "x".repeat(64) }),
        f,
        "2023-r01-R",
        10,
        1234.567,
      ),
      false,
    );
    assert.equal(geometryMatchesFrame(g, f), true);
  });

  it("PARTIAL frames render; unavailable drivers get no fake markers", () => {
    const f = frame({
      source_status: "PARTIAL",
      fresh_count: 1,
      unavailable_count: 1,
      drivers: [
        {
          driver_id: "hamilton",
          driver_number: 44,
          availability: "FRESH",
          observation_time_s: 1234.567,
          age_s: 0.0,
          render_x: 0.25,
          render_y: 0.75,
          outside_viewport: false,
        },
        {
          driver_id: "vettel",
          driver_number: 5,
          availability: "UNAVAILABLE",
          observation_time_s: null,
          age_s: null,
          render_x: null,
          render_y: null,
          outside_viewport: false,
        },
      ],
    });
    assert.equal(isPartialFrame(f), true);
    assert.equal(
      canRenderSpatialFrame(geometry(), f, "2023-r01-R", 10, 1234.567),
      true,
    );
    const markers = markerData(f);
    assert.equal(markers.length, 1);
    assert.equal(markers[0].driverId, "hamilton");
  });
});

describe("failure routing", () => {
  it("aborts are silent; unavailable is isolated; rest is panel error", () => {
    assert.equal(
      classifySpatialFailure(new DOMException("aborted", "AbortError")),
      "aborted",
    );
    assert.equal(
      classifySpatialFailure(new SpatialApiError(404, { error: "spatial_unavailable" })),
      "unavailable",
    );
    assert.equal(
      classifySpatialFailure(new SpatialApiError(404, { error: "unknown_race" })),
      "error",
    );
    assert.equal(classifySpatialFailure(new Error("boom")), "error");
  });
});

describe("selection scope", () => {
  it("passes the existing selection through only within its race", () => {
    assert.equal(
      spatialSelectionForRace("hamilton", "2023-r01-R", "2023-r01-R"),
      "hamilton",
    );
    assert.equal(
      spatialSelectionForRace("hamilton", "2023-r01-R", "2021-r05-R"),
      null,
    );
    assert.equal(spatialSelectionForRace(null, "2023-r01-R", "2023-r01-R"), null);
  });
});
