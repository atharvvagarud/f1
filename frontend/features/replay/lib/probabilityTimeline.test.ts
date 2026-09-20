import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { buildChartGeometry, checkpointAt, checkpointOrdinal, currentFrameAlignment, defaultVisibleDrivers, driverPeakProbabilities, isActualCheckpoint, probabilityAtCheckpoint } from "./probabilityTimeline.ts";
import type { ProbabilityTimelineResponse } from "@/lib/v2";

// Pure transforms + SVG geometry for R6. No DOM, no network, no pixel
// snapshots: only geometry/series-selection assertions.

function timeline(): ProbabilityTimelineResponse {
  return {
    race_id: "2023-r01-R",
    replay_contract_version: "v1",
    prediction_contract_version: "v1",
    probability_timeline_contract_version: "v1",
    probability_semantics: "INDEPENDENT_BINARY",
    model: {
      task: "winner",
      target: "is_winner",
      eligibility_mask: "eligible_is_winner",
      feature_set: "ALL_84",
      feature_set_version: "v8",
      estimator: "LogisticRegression",
      estimator_params: [],
      calibration_method: "RAW",
      probability_semantics: "INDEPENDENT_BINARY",
      training_seasons: [2018],
      transformed_dim: 106,
      feature_count: 84,
      artifact_sha256: "s",
      specification_fingerprint: "f",
      sklearn_version: "1.8.0",
    },
    timeline_identity: "identity",
    checkpoints: [
      { frame_index: 0, state_time_s: 0, leader_lap: 1, reasons: ["LEADER_LAP"] },
      { frame_index: 10, state_time_s: 100, leader_lap: 1, reasons: ["FLAG_TRANSITION"] },
      { frame_index: 25, state_time_s: 250, leader_lap: 2, reasons: ["LEADER_LAP"] },
    ],
    driver_series: [
      {
        driver_id: "a",
        points: [
          { frame_index: 0, state_time_s: 0, leader_lap: 1, winner_probability: 0.6 },
          { frame_index: 10, state_time_s: 100, leader_lap: 1, winner_probability: null },
          { frame_index: 25, state_time_s: 250, leader_lap: 2, winner_probability: 1.15 },
        ],
      },
      {
        driver_id: "b",
        points: [
          { frame_index: 0, state_time_s: 0, leader_lap: 1, winner_probability: 0.55 },
          { frame_index: 10, state_time_s: 100, leader_lap: 1, winner_probability: 0.7 },
          { frame_index: 25, state_time_s: 250, leader_lap: 2, winner_probability: 0.4 },
        ],
      },
      {
        driver_id: "c",
        points: [
          { frame_index: 0, state_time_s: 0, leader_lap: 1, winner_probability: null },
          { frame_index: 10, state_time_s: 100, leader_lap: 1, winner_probability: 0.2 },
          { frame_index: 25, state_time_s: 250, leader_lap: 2, winner_probability: null },
        ],
      },
    ],
  };
}

describe("checkpoint lookup", () => {
  it("finds actual checkpoints only", () => {
    const t = timeline();
    assert.equal(isActualCheckpoint(t, 10), true);
    assert.equal(isActualCheckpoint(t, 11), false);
    assert.equal(checkpointOrdinal(t, 25), 2);
    assert.equal(checkpointOrdinal(t, 11), -1);
    assert.equal(checkpointAt(t, 10)?.reasons[0], "FLAG_TRANSITION");
    assert.equal(checkpointAt(t, 11), null);
  });

  it("reads a driver's probability at a checkpoint without fill", () => {
    const t = timeline();
    const a = t.driver_series[0];
    assert.equal(probabilityAtCheckpoint(a, 0), 0.6);
    assert.equal(probabilityAtCheckpoint(a, 10), null); // null preserved
    assert.equal(probabilityAtCheckpoint(a, 11), null); // absent, never filled
  });
});

describe("driver visibility selection", () => {
  it("defaults deterministically to top-N by peak probability", () => {
    const t = timeline();
    assert.deepEqual(defaultVisibleDrivers(t, 2), ["a", "b"]);
    assert.deepEqual(defaultVisibleDrivers(t, 3), ["a", "b", "c"]);
    assert.deepEqual(defaultVisibleDrivers(t, 1), ["a"]);
  });

  it("breaks ties by driver_id ascending", () => {
    const t = timeline();
    const peaks = driverPeakProbabilities(t);
    peaks.set("a", 0.5);
    peaks.set("b", 0.5);
    peaks.set("c", 0.5);
    const ranks = [...t.driver_series]
      .map((s) => s.driver_id)
      .sort((x, y) => (peaks.get(y) ?? 0) - (peaks.get(x) ?? 0));
    assert.deepEqual(ranks, ["a", "b", "c"]);
  });
});

describe("current frame alignment", () => {
  it("reports an exact checkpoint", () => {
    const t = timeline();
    const a = currentFrameAlignment(t, 10);
    assert.equal(a.kind, "checkpoint");
    if (a.kind === "checkpoint") {
      assert.equal(a.ordinal, 1);
      assert.equal(a.markerX, 1);
    }
  });

  it("reports between-checkpoint position without inventing a value", () => {
    const t = timeline();
    const a = currentFrameAlignment(t, 5);
    assert.equal(a.kind, "between");
    if (a.kind === "between") {
      assert.equal(a.previousOrdinal, 0);
      assert.equal(a.nextOrdinal, 1);
      assert.equal(a.fraction, 0.5);
      assert.equal(a.markerX, 0.5);
    }
  });

  it("handles before-first, after-last and empty timelines", () => {
    const t = timeline();
    assert.equal(currentFrameAlignment(t, -1).kind, "before_first");
    assert.equal(currentFrameAlignment(t, 99).kind, "after_last");
    assert.equal(
      currentFrameAlignment({ ...t, checkpoints: [] }, 0).kind,
      "none",
    );
  });
});

describe("SVG geometry (rendering only)", () => {
  it("emits only actual checkpoint observations, breaking at null", () => {
    const t = timeline();
    const g = buildChartGeometry(t, ["a", "b", "c"], { width: 400, height: 200 });
    const a = g.series.find((s) => s.driverId === "a")!;
    assert.equal(a.segments.length, 2); // null between frame 0 and frame 25
    assert.deepEqual(a.segments.map((s) => s.length), [1, 1]);
    const c = g.series.find((s) => s.driverId === "c")!;
    assert.equal(c.segments.length, 1);
    assert.equal(c.segments[0][0].frameIndex, 10);
    const b = g.series.find((s) => s.driverId === "b")!;
    assert.equal(b.segments.length, 1);
    assert.deepEqual(b.segments[0].map((p) => p.frameIndex), [0, 10, 25]);
  });

  it("never plots a null as zero", () => {
    const t = timeline();
    const g = buildChartGeometry(t, ["a"], { width: 400, height: 200 });
    const points = g.series.flatMap((s) => s.segments.flat());
    assert.equal(points.length, 2); // a has one null -> not plotted
    assert.ok(points.every((p) => p.probability !== 0));
  });

  it("preserves >100% values without normalization", () => {
    const t = timeline();
    const g = buildChartGeometry(t, ["a", "b"], { width: 400, height: 200 });
    const a25 = g.series
      .find((s) => s.driverId === "a")!
      .segments.flat()
      .find((p) => p.frameIndex === 25)!;
    const b25 = g.series
      .find((s) => s.driverId === "b")!
      .segments.flat()
      .find((p) => p.frameIndex === 25)!;
    assert.equal(a25.probability, 1.15);
    assert.equal(b25.probability, 0.4);
    assert.ok(a25.probability + b25.probability > 1.0);
    assert.ok(g.yMax >= 1.15);
  });

  it("filters to visible drivers while leaving the data untouched", () => {
    const t = timeline();
    const g = buildChartGeometry(t, ["b"], { width: 400, height: 200 });
    assert.deepEqual(g.series.map((s) => s.driverId), ["b"]);
    // Source timeline still has every driver + null.
    assert.equal(t.driver_series.length, 3);
    assert.equal(t.driver_series[0].points[1].winner_probability, null);
  });
});
