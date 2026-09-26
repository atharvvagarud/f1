import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { NEUTRAL_DISPLAY_TOLERANCE, changeOmittedNote, changeResidualWithinTolerance, defaultChangeDriver, deltaArrow, deltaWord, formatLogOdds, formatPercentagePoints, formatProbabilityPercent, previousCheckpoint, probabilityChange, transitionMarker } from "./timelineChange.ts";
import type {
  ProbabilityTimelineResponse,
  TimelineChangeResponse,
} from "@/lib/v2";

const HERE = dirname(fileURLToPath(import.meta.url));

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
        driver_id: "verstappen",
        points: [
          { frame_index: 0, state_time_s: 0, leader_lap: 1, winner_probability: 0.42 },
          { frame_index: 10, state_time_s: 100, leader_lap: 1, winner_probability: null },
          { frame_index: 25, state_time_s: 250, leader_lap: 2, winner_probability: 0.578 },
        ],
      },
      {
        driver_id: "hamilton",
        points: [
          { frame_index: 0, state_time_s: 0, leader_lap: 1, winner_probability: 0.1 },
          { frame_index: 10, state_time_s: 100, leader_lap: 1, winner_probability: 0.2 },
          { frame_index: 25, state_time_s: 250, leader_lap: 2, winner_probability: 0.05 },
        ],
      },
    ],
  };
}

function change(): TimelineChangeResponse {
  return {
    contract_version: "v1",
    format: "timeline-explanation-v1",
    status: "AVAILABLE",
    identity: {
      race_id: "2023-r01-R",
      driver_id: "verstappen",
      from_frame_index: 0,
      to_frame_index: 25,
      from_checkpoint: {
        frame_index: 0,
        state_time_s: 0,
        leader_lap: 1,
        reasons: ["LEADER_LAP"],
        anchor_driver_id: "verstappen",
        anchor_lap_number: 1,
        anchor_state_time_s: 0,
        observed_lap_number: 1,
        observed_time_s: 0,
        observed_position: 1,
        observation_age_s: 0,
      },
      to_checkpoint: {
        frame_index: 25,
        state_time_s: 250,
        leader_lap: 2,
        reasons: ["LEADER_LAP"],
        anchor_driver_id: "verstappen",
        anchor_lap_number: 25,
        anchor_state_time_s: 250,
        observed_lap_number: 25,
        observed_time_s: 250,
        observed_position: 1,
        observation_age_s: 0,
      },
    },
    model_identity: null,
    probability_semantics: "INDEPENDENT_BINARY",
    explanation_space: "LOG_ODDS",
    reason: null,
    from_probability: 0.42,
    to_probability: 0.578,
    probability_delta: 0.158,
    from_logit: -0.32,
    to_logit: 0.31,
    logit_delta: 0.63,
    cached_from_probability: 0.42,
    cached_to_probability: 0.578,
    reconstruction: {
      from_logit: -0.32,
      to_logit: 0.31,
      logit_delta: 0.63,
      canonical_delta_sum: 0.63,
      residual: 1e-16,
      logit_abs_tolerance: 1e-12,
      probability_abs_tolerance: 1e-12,
      intercept_cancels: true,
      full_decomposition_reconstructs_change: true,
    },
    canonical_feature_count: 84,
    top_positive: [
      {
        canonical_feature: "gap_to_leader_seconds",
        feature_family: "GAPS",
        feature_type: "numeric",
        from_raw_value: 12.5,
        to_raw_value: 3.1,
        from_input_state: "OBSERVED",
        to_input_state: "OBSERVED",
        from_active_category: null,
        to_active_category: null,
        from_contribution: -0.1,
        to_contribution: 0.31,
        contribution_delta: 0.41,
        transition: "RAW_INPUT_CHANGED",
      },
    ],
    top_negative: [
      {
        canonical_feature: "tyre_age_laps",
        feature_family: "STATE",
        feature_type: "numeric",
        from_raw_value: 12,
        to_raw_value: 20,
        from_input_state: "OBSERVED",
        to_input_state: "OBSERVED",
        from_active_category: null,
        to_active_category: null,
        from_contribution: 0.0,
        to_contribution: -0.08,
        contribution_delta: -0.08,
        transition: "RAW_INPUT_CHANGED",
      },
    ],
    accounting: {
      top_n: 5,
      total_positive_log_odds_delta: 0.55,
      total_negative_log_odds_delta: 0.08,
      shown_positive_log_odds_delta: 0.41,
      shown_negative_log_odds_delta: -0.08,
      omitted_positive_log_odds_delta: 0.14,
      omitted_negative_log_odds_delta: 0.16,
      positive_feature_count: 12,
      negative_feature_count: 9,
      full_decomposition_reconstructs_change: true,
      top_n_reconstructs_change: false,
      note: "compact view",
    },
    limitations: ["not causal"],
    cache_status: "HIT",
  };
}

describe("timeline change display transforms", () => {
  it("finds the previous REAL checkpoint without snapping", () => {
    assert.equal(previousCheckpoint(timeline(), 25)?.frame_index, 10);
    assert.equal(previousCheckpoint(timeline(), 10)?.frame_index, 0);
    assert.equal(previousCheckpoint(timeline(), 0), null);
    assert.equal(previousCheckpoint(timeline(), 7)?.frame_index, 0);
  });

  it("never snaps a non-checkpoint frame to itself or a future checkpoint", () => {
    assert.equal(previousCheckpoint(timeline(), 7)?.frame_index, 0);
    assert.equal(previousCheckpoint(timeline(), 24)?.frame_index, 10);
    assert.equal(previousCheckpoint(timeline(), 25)?.frame_index, 10);
  });

  it("formats log-odds deltas with an explicit sign", () => {
    assert.equal(formatLogOdds(0.63), "+0.63");
    assert.equal(formatLogOdds(-0.08), "-0.08");
    assert.equal(formatLogOdds(0), "0.00");
    assert.equal(formatLogOdds(Number.NaN), "n/a");
  });

  it("computes the overall probability change and preserves nulls", () => {
    const hamilton = probabilityChange(timeline(), "hamilton", 25);
    assert.equal(hamilton.from, 0.2);
    assert.equal(hamilton.to, 0.05);
    assert.ok(Math.abs((hamilton.delta ?? 0) + 0.15) < 1e-12);
    // Previous checkpoint frame 10 is unevaluated for verstappen: no delta.
    assert.deepEqual(probabilityChange(timeline(), "verstappen", 25), {
      from: null,
      to: 0.578,
      delta: null,
    });
    assert.deepEqual(probabilityChange(timeline(), "verstappen", 10), {
      from: 0.42,
      to: null,
      delta: null,
    });
    assert.deepEqual(probabilityChange(timeline(), "verstappen", 0), {
      from: null,
      to: null,
      delta: null,
    });
  });

  it("picks a default visible driver deterministically", () => {
    assert.equal(defaultChangeDriver(timeline(), 25), "verstappen");
    assert.equal(defaultChangeDriver(timeline(), 10), "hamilton");
  });

  it("formats the overall change in percentage points only", () => {
    assert.equal(formatProbabilityPercent(0.578), "57.8%");
    assert.equal(formatProbabilityPercent(null), null);
    assert.equal(formatPercentagePoints(0.158), "+15.8pp");
    assert.equal(formatPercentagePoints(-0.03), "-3.0pp");
    assert.equal(formatPercentagePoints(null), null);
  });

  it("classifies delta arrows with a presentational-only threshold", () => {
    assert.equal(NEUTRAL_DISPLAY_TOLERANCE > 0, true);
    assert.equal(deltaArrow(0.41), "\u2191");
    assert.equal(deltaArrow(-0.08), "\u2193");
    assert.equal(deltaArrow(0), "\u00b7");
    assert.equal(deltaWord(0.41), "INCREASED MODEL LOG-ODDS");
    assert.equal(deltaWord(-0.08), "DECREASED MODEL LOG-ODDS");
    assert.equal(deltaWord(0), "NEUTRAL");
  });

  it("marks transitions factually", () => {
    assert.equal(transitionMarker("IMPUTATION_TRANSITION"), "IMPUTED");
    assert.equal(transitionMarker("MISSINGNESS_TRANSITION"), "MISSING");
    assert.equal(transitionMarker("CATEGORICAL_TRANSITION"), "CATEGORY");
    assert.equal(transitionMarker("RAW_INPUT_UNCHANGED"), null);
  });

  it("reports omitted delta accounting and residual tolerance", () => {
    const note = changeOmittedNote(change().accounting!);
    assert.match(note, /omitted/);
    assert.match(note, /top list does not/);
    assert.equal(changeResidualWithinTolerance(change()), true);
  });
});

describe("change explanation language contract (frontend copy)", () => {
  const files = [
    join(HERE, "timelineChange.ts"),
    join(HERE, "..", "components", "ChangeExplanationPanel.tsx"),
    join(HERE, "..", "hooks", "useTimelineChange.ts"),
  ];

  it("never uses forbidden causal / per-feature probability labels", () => {
    const forbidden = [
      "CAUSED",
      "BECAUSE",
      "ADDED 12%",
      "+12% CHANCE",
      "PROBABILITY POINTS",
      "WIN SHARE",
      "MADE THE DRIVER",
    ];
    for (const file of files) {
      const text = readFileSync(file, "utf8").toUpperCase();
      for (const phrase of forbidden) {
        assert.equal(text.includes(phrase), false, `${file}: ${phrase}`);
      }
    }
  });

  it("uses model log-odds delta wording, not per-feature percentages", () => {
    const panel = readFileSync(files[1], "utf8");
    assert.match(panel, /Model score change/i);
    assert.match(panel, /log-odds/i);
    assert.match(panel, /since the previous checkpoint/i);
  });
});
