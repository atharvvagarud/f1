import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { formatDriverName, formatGap, formatPercent, formatWhole, getConfidenceTone, titleCaseModelName } from "./predictionHelpers.ts";

// Characterisation tests for the pure presentation helpers used across the
// prediction page. No DOM, no framework, no new dependencies:
// run with `node --test lib/predictionHelpers.test.ts` (Node >= 22).

describe("formatPercent", () => {
  it("formats a fraction as one-decimal percent", () => {
    assert.equal(formatPercent(0.8051), "80.5%");
    assert.equal(formatPercent(0), "0.0%");
    assert.equal(formatPercent(1), "100.0%");
  });
});

describe("formatGap", () => {
  it("formats seconds with two decimals", () => {
    assert.equal(formatGap(3.456), "3.46s");
    assert.equal(formatGap(0), "0.00s");
  });

  it("renders missing values as an em dash (current UI contract)", () => {
    assert.equal(formatGap(null), "—");
    assert.equal(formatGap(undefined), "—");
    assert.equal(formatGap(NaN), "—");
  });
});

describe("formatWhole", () => {
  it("rounds positions", () => {
    assert.equal(formatWhole(1.0), "1");
    assert.equal(formatWhole(2.4), "2");
  });

  it("renders missing values as an em dash", () => {
    assert.equal(formatWhole(null), "—");
    assert.equal(formatWhole(undefined), "—");
    assert.equal(formatWhole(NaN), "—");
  });
});

describe("getConfidenceTone", () => {
  it("uses emerald at >= 0.75", () => {
    assert.match(getConfidenceTone(0.75).pill, /emerald/);
    assert.match(getConfidenceTone(0.9).bar, /emerald/);
  });

  it("uses amber at >= 0.55 and below 0.75", () => {
    assert.match(getConfidenceTone(0.55).pill, /amber/);
    assert.match(getConfidenceTone(0.749).pill, /amber/);
  });

  it("uses red below 0.55", () => {
    assert.match(getConfidenceTone(0.549).pill, /red/);
    assert.match(getConfidenceTone(0).bar, /red/);
  });
});

describe("titleCaseModelName", () => {
  it("maps internal and display names to display names", () => {
    assert.equal(titleCaseModelName("logreg"), "Logistic Regression");
    assert.equal(titleCaseModelName("hgb"), "HistGradientBoosting");
    assert.equal(titleCaseModelName("xgboost"), "XGBoost");
    assert.equal(titleCaseModelName("XGBoost"), "XGBoost");
  });

  it("passes unknown names through unchanged", () => {
    assert.equal(titleCaseModelName("my-model"), "my-model");
  });
});

describe("formatDriverName", () => {
  it("expands known codes", () => {
    assert.equal(formatDriverName("VER"), "Max Verstappen");
    assert.equal(formatDriverName("HAM"), "Lewis Hamilton");
  });

  it("returns N/A for missing and passes unknown codes through", () => {
    assert.equal(formatDriverName(null), "N/A");
    assert.equal(formatDriverName(undefined), "N/A");
    assert.equal(formatDriverName("XYZ"), "XYZ");
  });
});
