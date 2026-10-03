import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { SPATIAL_VIEWBOX, SpatialApiError, formatSvgCoord, geometryMatchesFrame, getSpatialFrame, getSpatialGeometry, getSpatialWindow, isPartialFrame, markerData, markerLabel, toSvgX, toSvgY, trackPath, trailPath, unplottedDrivers, type SpatialDriverState, type SpatialFetchLike, type SpatialFrame, type SpatialGeometry } from "./spatial.ts";

// Characterisation tests for the P12-6 spatial client + view-model
// (lib/spatial.ts): endpoint URLs, error parsing, deterministic SVG
// mapping, availability presentation, geometry identity, no-mutation.
// fetch is stubbed — no network, no server.
// Run with `node --test lib/spatial.test.ts` (Node >= 22).

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];
let stubBody: unknown;
let stubStatus: number;

function stubFetch(
  body: unknown,
  status = 200,
): { fetcher: SpatialFetchLike; calls: () => FetchCall[] } {
  calls = [];
  stubBody = body;
  stubStatus = status;
  const fetcher: SpatialFetchLike = async (url, init) => {
    calls.push({ url, init });
    return { ok: stubStatus >= 200 && stubStatus < 300, status: stubStatus, json: async () => stubBody };
  };
  return { fetcher, calls: () => calls };
}

function geometry(over: Partial<SpatialGeometry> = {}): SpatialGeometry {
  return {
    race_id: "2023-r01-R",
    schema_version: "spatial-geometry-v1",
    algorithm_version: "p12-3-v1",
    geometry_sha256: "g".repeat(64),
    main_track: { points: [[0, 0], [1, 0], [1, 1], [0, 1]], n_points: 4, closed_loop: true },
    pit_lane: null,
    pit_status: "PIT_GEOMETRY_DEFERRED",
    render_bounds: { u_min: 0, v_min: 0, u_max: 1, v_max: 1 },
    ...over,
  };
}

function driver(over: Partial<SpatialDriverState> = {}): SpatialDriverState {
  return {
    driver_id: "hamilton",
    driver_number: 44,
    availability: "FRESH",
    observation_time_s: 12.0,
    age_s: 0.0,
    render_x: 0.25,
    render_y: 0.75,
    outside_viewport: false,
    ...over,
  };
}

function frame(drivers: SpatialDriverState[]): SpatialFrame {
  const fresh = drivers.filter((d) => d.availability === "FRESH").length;
  const stale = drivers.filter((d) => d.availability === "STALE").length;
  return {
    race_id: "2023-r01-R",
    frame_index: 0,
    query_time_s: 12.0,
    source_status: "COMPLETE",
    geometry_sha256: "g".repeat(64),
    observation_content_sha256: "o".repeat(64),
    resolver_contract_version: "spatial-resolver-v1",
    fresh_count: fresh,
    stale_count: stale,
    unavailable_count: drivers.length - fresh - stale,
    drivers,
  };
}

describe("exact coordinate mapping", () => {
  it("maps render 0.25/0.75 onto the viewBox exactly", () => {
    assert.equal(toSvgX(0.25), 250);
    assert.equal(toSvgY(0.75), 750);
    assert.equal(SPATIAL_VIEWBOX, 1000);
  });

  it("builds a deterministic closed path without altering points", () => {
    const d = trackPath([[0.25, 0.75], [0.5, 0.5]], true);
    assert.equal(d, "M250 750 L500 500 Z");
    assert.equal(trackPath([[0.25, 0.75], [0.5, 0.5]], false), "M250 750 L500 500");
  });

  it("quantizes deterministically to milli-units", () => {
    assert.equal(formatSvgCoord(233.444333 * 1), "233.444");
    assert.equal(trackPath([[1 / 3, 2 / 3]], false), "M333.333 666.667");
  });
});

describe("availability presentation", () => {
  it("renders FRESH and STALE, omits UNAVAILABLE", () => {
    const data = markerData(
      frame([driver(), driver({ driver_id: "leclerc", driver_number: 16, availability: "STALE", age_s: 12.0 }), driver({ driver_id: "sainz", driver_number: 55, availability: "UNAVAILABLE", observation_time_s: null, age_s: null, render_x: null, render_y: null })]),
    );
    assert.deepEqual(data.map((m) => m.label), ["44", "16"]);
    assert.equal(data[1].availability, "STALE");
  });

  it("omits rows with null coordinates even when marked available", () => {
    const data = markerData(frame([driver({ render_x: null })]));
    assert.equal(data.length, 0);
  });

  it("preserves frame order and exact positions", () => {
    const data = markerData(
      frame([driver({ driver_number: 1, render_x: 0.1, render_y: 0.2 }), driver({ driver_number: 44, render_x: 0.3, render_y: 0.4 })]),
    );
    assert.deepEqual(data.map((m) => m.cx), [100, 300]);
    assert.deepEqual(data.map((m) => m.cy), [200, 400]);
  });

  it("labels prefer driver number, fall back to driver id", () => {
    assert.equal(markerLabel(driver({ driver_number: 44 })), "44");
    assert.equal(markerLabel(driver({ driver_number: null, driver_id: "rookie" })), "rookie");
  });

  it("never clamps outside-viewport coordinates", () => {
    const data = markerData(frame([driver({ render_x: 1.2, render_y: -0.1, outside_viewport: true })]));
    assert.equal(data.length, 1);
    assert.equal(data[0].cx, 1200);
    assert.equal(data[0].cy, -100);
    assert.equal(data[0].outsideViewport, true);
  });

  it("lists unplotted drivers for coverage metadata", () => {
    const f = frame([driver(), driver({ driver_id: "sainz", driver_number: 55, availability: "UNAVAILABLE", observation_time_s: null, age_s: null, render_x: null, render_y: null })]);
    assert.equal(unplottedDrivers(f).length, 1);
    assert.equal(isPartialFrame({ ...f, source_status: "PARTIAL" }), true);
    assert.equal(isPartialFrame(f), false);
  });
});

describe("geometry identity", () => {
  it("matches only on identical race + sha", () => {
    const g = geometry();
    const f = frame([driver()]);
    assert.equal(geometryMatchesFrame(g, f), true);
    assert.equal(geometryMatchesFrame(g, { ...f, geometry_sha256: "x".repeat(64) }), false);
    assert.equal(geometryMatchesFrame(g, { ...f, geometry_sha256: null }), false);
    assert.equal(geometryMatchesFrame({ ...g, race_id: "2021-r05-R" }, f), false);
  });
});

describe("trail primitive", () => {
  it("renders supplied samples verbatim in order", () => {
    const d = trailPath([
      { observation_time_s: 10, render_x: 0.1, render_y: 0.1 },
      { observation_time_s: 11, render_x: 0.2, render_y: 0.2 },
      { observation_time_s: 12, render_x: 0.3, render_y: 0.3 },
    ]);
    assert.equal(d, "M100 100 L200 200 L300 300");
  });

  it("skips null-coordinate samples without reordering", () => {
    const d = trailPath([
      { observation_time_s: 10, render_x: 0.1, render_y: 0.1 },
      { observation_time_s: 11, render_x: null, render_y: null },
    ]);
    assert.equal(d, "M100 100");
  });

  it("is empty for no samples", () => {
    assert.equal(trailPath([]), "");
  });
});

describe("spatial client", () => {
  it("fetches geometry from the canonical path", async () => {
    const g = geometry();
    const { fetcher, calls: got } = stubFetch(g);
    const out = await getSpatialGeometry("2023-r01-R", fetcher);
    assert.deepEqual(out, g);
    assert.equal(got()[0].url, "http://127.0.0.1:8000/v2/races/2023-r01-R/spatial/geometry");
  });

  it("fetches frame and window from canonical paths", async () => {
    const f = frame([driver()]);
    const { fetcher, calls: got } = stubFetch(f);
    await getSpatialFrame("2023-r01-R", 7, fetcher);
    assert.equal(got()[0].url, "http://127.0.0.1:8000/v2/races/2023-r01-R/spatial/frame/7");
    const { fetcher: w } = stubFetch({ samples: [] });
    await getSpatialWindow("2023-r01-R", 7, 44, 5, w);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/v2/races/2023-r01-R/spatial/window/7?driver_number=44&history_s=5");
  });

  it("parses spatial errors with predicates", async () => {
    const { fetcher } = stubFetch({ error: "spatial_unavailable", detail: "no servable state" }, 404);
    await assert.rejects(() => getSpatialFrame("2024-r09-R", 0, fetcher), (err: unknown) => {
      assert.ok(err instanceof SpatialApiError);
      assert.equal(err.isUnavailable(), true);
      assert.equal(err.isUnknownRace(), false);
      return true;
    });
    const { fetcher: bad } = stubFetch({ error: "spatial_integrity_error", detail: "mismatch" }, 500);
    await assert.rejects(() => getSpatialGeometry("2023-r01-R", bad), (err: unknown) => {
      assert.ok(err instanceof SpatialApiError && err.isIntegrityError());
      return true;
    });
  });
});

describe("no input mutation", () => {
  it("freezes fixtures through mapping", () => {
    const g = geometry();
    const f = frame([driver(), driver({ driver_number: 1 })]);
    Object.freeze(g);
    Object.freeze(g.main_track);
    Object.freeze(g.main_track.points);
    Object.freeze(f);
    Object.freeze(f.drivers);
    for (const d of f.drivers) Object.freeze(d);
    assert.doesNotThrow(() => {
      trackPath(g.main_track.points, true);
      markerData(f);
      geometryMatchesFrame(g, f);
      unplottedDrivers(f);
    });
  });
});
