import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { contributionArrow, directionWord, formatLogOdds, inputStateMarker, omittedNote, residualWithinTolerance, topContributions } from "./localExplanation.ts";
import type { LocalExplanationResponse } from "@/lib/v2";

const HERE = dirname(fileURLToPath(import.meta.url));

function explanation(): LocalExplanationResponse {
  return {
    contract_version: "v1",
    format: "local-explanation-v1",
    identity: {
      race_id: "2023-r01-R",
      frame_index: 0,
      driver_id: "verstappen",
      checkpoint_reasons: ["LEADER_LAP"],
      leader_lap: 1,
      state_time_s: 0,
      anchor_driver_id: "verstappen",
      anchor_lap_number: 1,
      anchor_state_time_s: 0,
      feature_identity: {
        race_id: "2023-r01-R",
        driver_id: "verstappen",
        lap_number: 1,
        state_time_s: 0,
      },
      observation: {
        observed_lap_number: 1,
        observed_time_s: 0,
        observation_age_s: 0,
        observed_position: 1,
      },
    },
    model_identity: {
      feature_set: "ALL_84",
      feature_set_version: "v8",
      estimator_class: "LogisticRegression",
      specification_fingerprint: "spec",
      transformed_dim: 106,
      canonical_feature_count: 84,
      calibration_method: "RAW",
      probability_kind: "BINARY_PROBABILITY",
      probability_semantics: "INDEPENDENT_BINARY",
      training_seasons: [2018],
      sklearn_version: "1.8.0",
    },
    probability_semantics: "INDEPENDENT_BINARY",
    explanation_space: "LOG_ODDS",
    intercept: -5.57,
    logit: 1.5,
    probability: 0.81,
    model_probability: 0.81,
    cached_probability: 0.81,
    reconstruction: {
      estimator_decision_function: 1.5,
      residual: 1e-16,
      logit_abs_tolerance: 1e-12,
      probability_abs_tolerance: 1e-12,
      transformed_contribution_sum: 7.07,
      canonical_contribution_sum: 7.07,
    },
    transformed_feature_count: 106,
    canonical_feature_count: 84,
    top_positive: [
      {
        canonical_feature: "gap_to_leader_seconds",
        feature_family: "GAPS",
        feature_type: "numeric",
        raw_value: 1.2,
        input_state: "OBSERVED",
        imputed_value: null,
        active_category: null,
        log_odds_contribution: 1.24,
        direction: "INCREASES_MODEL_LOG_ODDS",
      },
      {
        canonical_feature: "position",
        feature_family: "STATE",
        feature_type: "numeric",
        raw_value: null,
        input_state: "IMPUTED_NUMERIC_MEDIAN",
        imputed_value: 8,
        active_category: null,
        log_odds_contribution: 0.81,
        direction: "INCREASES_MODEL_LOG_ODDS",
      },
    ],
    top_negative: [
      {
        canonical_feature: "tyre_age_laps",
        feature_family: "STATE",
        feature_type: "numeric",
        raw_value: 12,
        input_state: "OBSERVED",
        imputed_value: null,
        active_category: null,
        log_odds_contribution: -0.22,
        direction: "DECREASES_MODEL_LOG_ODDS",
      },
    ],
    accounting: {
      top_n: 5,
      total_positive_log_odds: 3.0,
      total_negative_log_odds: -0.4,
      shown_positive_log_odds: 2.05,
      shown_negative_log_odds: -0.22,
      omitted_positive_log_odds: 0.95,
      omitted_negative_log_odds: -0.18,
      positive_feature_count: 20,
      negative_feature_count: 18,
      full_decomposition_reconstructs_prediction: true,
      top_n_reconstructs_prediction: false,
      note: "Top contributions are a compact view.",
    },
    limitations: ["not causal"],
    cache_status: "HIT",
  };
}

describe("local explanation display transforms", () => {
  it("formats signed log-odds deterministically", () => {
    assert.equal(formatLogOdds(1.239), "+1.24");
    assert.equal(formatLogOdds(-0.22), "-0.22");
    assert.equal(formatLogOdds(0), "0.00");
    assert.equal(formatLogOdds(Number.NaN), "n/a");
  });

  it("maps direction to arrows and allowed words", () => {
    assert.equal(contributionArrow("INCREASES_MODEL_LOG_ODDS"), "\u2191");
    assert.equal(contributionArrow("DECREASES_MODEL_LOG_ODDS"), "\u2193");
    assert.equal(contributionArrow("NEUTRAL"), "\u00b7");
    assert.equal(directionWord("INCREASES_MODEL_LOG_ODDS"),
      "INCREASED MODEL LOG-ODDS");
    assert.equal(directionWord("DECREASES_MODEL_LOG_ODDS"),
      "DECREASED MODEL LOG-ODDS");
    assert.equal(directionWord("NEUTRAL"), "NEUTRAL");
  });

  it("marks imputed / missing / unknown inputs", () => {
    assert.equal(inputStateMarker("OBSERVED"), null);
    assert.equal(inputStateMarker("IMPUTED_NUMERIC_MEDIAN"), "IMPUTED");
    assert.equal(inputStateMarker("IMPUTED_BOOLEAN_MODE"), "IMPUTED");
    assert.equal(inputStateMarker("MISSING_CATEGORY"), "MISSING");
    assert.equal(inputStateMarker("UNKNOWN_CATEGORY"),
      "UNKNOWN TO FITTED ENCODER");
  });

  it("keeps determinism and never re-sorts backend order", () => {
    const view = topContributions(explanation());
    assert.deepEqual(view.positive.map((r) => r.canonical_feature),
      ["gap_to_leader_seconds", "position"]);
    assert.deepEqual(view.negative.map((r) => r.canonical_feature),
      ["tyre_age_laps"]);
  });

  it("reports omitted accounting and residual tolerance", () => {
    const note = omittedNote(explanation().accounting);
    assert.match(note, /omitted \+\d+\.\d+ positive/);
    assert.match(note, /top list does not/);
    assert.equal(residualWithinTolerance(explanation()), true);
  });
});

describe("local explanation language contract (frontend copy)", () => {
  const files = [
    join(HERE, "localExplanation.ts"),
    join(HERE, "..", "components", "LocalExplanationPanel.tsx"),
    join(HERE, "..", "hooks", "useLocalExplanation.ts"),
  ];

  it("never uses forbidden win-probability / causal labels", () => {
    const forbidden = [
      "WHY THEY WILL WIN",
      "WIN FACTORS",
      "CHANCE ADDED",
      "REASONS FOR WINNING",
      "+12% CHANCE",
      "PROBABILITY POINTS",
      "WIN SHARE",
    ];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const phrase of forbidden) {
        assert.equal(text.includes(phrase), false, `${file}: ${phrase}`);
      }
    }
  });

  it("uses model log-odds wording", () => {
    const panel = readFileSync(files[1], "utf8");
    assert.match(panel, /Model log-odds/i);
    assert.match(panel, /INCREASED MODEL LOG-ODDS/i);
    assert.match(panel, /DECREASED MODEL LOG-ODDS/i);
    assert.match(panel, /log-odds contributions, not/);
  });
});
