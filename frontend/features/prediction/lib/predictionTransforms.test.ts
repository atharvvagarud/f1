import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { buildChartRows, groupEnsembleSummaryByLap } from "./predictionTransforms.ts";
import type { EnsembleResult, SingleModelResult } from "../../../lib/predictionTypes";

// Characterisation tests for the view-model transforms used by the
// prediction page (grouping/sorting of chart rows and summary tables).
// Run with `node --test features/prediction/lib/predictionTransforms.test.ts`.

const ensemble: EnsembleResult = {
  summary: [
    {
      lap: 10,
      model: "XGBoost",
      predicted_winner: "VER",
      win_probability: 0.6,
      actual_winner: "VER",
      actual_rank: 1,
    },
    {
      lap: 5,
      model: "XGBoost",
      predicted_winner: "HAM",
      win_probability: 0.4,
      actual_winner: "VER",
      actual_rank: 2,
    },
    {
      lap: 5,
      model: "Logistic Regression",
      predicted_winner: "HAM",
      win_probability: 0.3,
      actual_winner: "VER",
      actual_rank: 2,
    },
  ],
  latest_lap: 10,
  final_winner: "VER",
  decision_reason: "Majority vote at latest checkpoint",
  actual_winner: "VER",
  agreement_count: 3,
  confidence_value: 0.6,
  confidence_label: "Confidence (XGBoost)",
  latest_top5: {},
};

const single: SingleModelResult = {
  summary: [
    {
      lap: 10,
      predicted_winner: "VER",
      win_probability: 0.6,
      actual_winner: "VER",
      actual_rank: 1,
    },
    {
      lap: 5,
      predicted_winner: "HAM",
      win_probability: 0.4,
      actual_winner: "VER",
      actual_rank: 2,
    },
  ],
  latest: {
    model: "xgboost",
    lap: 10,
    predicted_winner: "VER",
    predicted_driver_number: 1,
    predicted_win_probability: 0.6,
    actual_winner: "VER",
    actual_rank: 1,
    top5: [],
  },
};

describe("buildChartRows", () => {
  it("groups ensemble rows by model and sorts laps ascending", () => {
    const rows = buildChartRows("ensemble", "xgboost", ensemble, null);
    assert.deepEqual(Object.keys(rows).sort(), [
      "Logistic Regression",
      "XGBoost",
    ]);
    assert.deepEqual(rows["XGBoost"], [
      { lap: 5, value: 0.4 },
      { lap: 10, value: 0.6 },
    ]);
  });

  it("maps single-model summaries under the uppercased model id", () => {
    const rows = buildChartRows("single", "hgb", null, single);
    assert.deepEqual(rows, {
      HGB: [
        { lap: 10, value: 0.6 },
        { lap: 5, value: 0.4 },
      ],
    });
  });

  it("returns empty groups without a result", () => {
    assert.deepEqual(buildChartRows("ensemble", "xgboost", null, null), {});
    assert.deepEqual(buildChartRows("single", "xgboost", null, null), {});
  });
});

describe("groupEnsembleSummaryByLap", () => {
  it("buckets summary rows by lap checkpoint", () => {
    const grouped = groupEnsembleSummaryByLap(ensemble.summary);
    assert.deepEqual(
      Object.keys(grouped).map(Number).sort((a, b) => a - b),
      [5, 10],
    );
    assert.equal(grouped[5].length, 2);
    assert.equal(grouped[10].length, 1);
  });
});
