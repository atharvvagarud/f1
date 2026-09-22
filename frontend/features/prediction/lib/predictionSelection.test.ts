import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { sameSelection } from "./predictionSelection.ts";
import type { PredictionSelection } from "./predictionSelection.ts";

// Characterisation of the UI6 stale-result rule: a stored prediction belongs to
// the exact season + Grand Prix + mode + model that produced it. Changing any
// part means the old result is invalid and must not be displayed (or re-labelled
// with the new selection). Run with `node --test`.

const base: PredictionSelection = {
  year: 2023,
  event: "Abu Dhabi Grand Prix",
  mode: "ensemble",
  model: "xgboost",
};

describe("prediction selection identity", () => {
  it("matches only the exact producing selection", () => {
    assert.equal(sameSelection(base, { ...base }), true);
  });

  it("rejects a changed season", () => {
    assert.equal(sameSelection(base, { ...base, year: 2022 }), false);
  });

  it("rejects a changed Grand Prix (the documented stale-result bug)", () => {
    assert.equal(
      sameSelection(base, { ...base, event: "Bahrain Grand Prix" }),
      false,
    );
  });

  it("rejects a changed mode", () => {
    assert.equal(sameSelection(base, { ...base, mode: "single" }), false);
  });

  it("rejects a changed single-model family", () => {
    assert.equal(
      sameSelection({ ...base, mode: "single" }, { ...base, mode: "single", model: "logreg" }),
      false,
    );
  });

  it("treats a missing result selection as never current", () => {
    assert.equal(sameSelection(null, base), false);
    assert.equal(sameSelection(base, null), false);
    assert.equal(sameSelection(null, null), false);
  });
});
