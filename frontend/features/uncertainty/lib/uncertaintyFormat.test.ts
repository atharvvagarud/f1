// Uncertainty display-contract unit tests (V3.9D). Pure functions only.
// Run with: node --test features/uncertainty/lib/uncertaintyFormat.test.ts
import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { formatAbsGap, formatBound, formatCount, formatJaccard, formatProb, formatRank, formatSE, formatSignedGap, formatSpearman, gapDirection, leaderWording, statusLabel } from "./uncertaintyFormat.ts";

describe("probability formatting (0.000 contract)", () => {
  it("renders three decimals deterministically", () => {
    assert.equal(formatProb(0.742), "0.742");
    assert.equal(formatProb(0.031), "0.031");
    assert.equal(formatProb(1), "1.000");
  });
  it("valid zero renders as 0.000, never missing", () => {
    assert.equal(formatProb(0), "0.000");
    assert.notEqual(formatProb(0), "—");
    assert.notEqual(formatProb(0), "N/A");
  });
  it("null/undefined/NaN stay null (unavailable is not zero)", () => {
    assert.equal(formatProb(null), null);
    assert.equal(formatProb(undefined), null);
    assert.equal(formatProb(NaN), null);
  });
  it("tiny nonzero values keep the 3-decimal rule deterministically", () => {
    assert.equal(formatProb(0.0003461), "0.000");
    assert.equal(formatProb(0.0006), "0.001");
  });
});

describe("gap formatting", () => {
  it("sign convention: + means simulation higher", () => {
    assert.equal(formatSignedGap(0.001234), "+0.001");
    assert.equal(formatSignedGap(-0.001234), "−0.001");
    assert.equal(formatSignedGap(0), "0.000");
  });
  it("absolute gap is unsigned magnitude", () => {
    assert.equal(formatAbsGap(-0.001234), "0.001");
    assert.equal(formatAbsGap(0), "0.000");
  });
  it("direction wording is never color-only", () => {
    assert.equal(gapDirection(0.5), "simulation higher");
    assert.equal(gapDirection(-0.5), "model higher");
    assert.equal(gapDirection(0), "equal");
    assert.equal(gapDirection(null), "direction unavailable");
  });
});

describe("sampling precision formatting", () => {
  it("SE and Wilson bounds use 4 decimals", () => {
    assert.equal(formatSE(0.000346306), "0.0003");
    assert.equal(formatBound(0.0002040709), "0.0002");
    assert.equal(formatBound(1), "1.0000");
  });
  it("Wilson boundary cases render, never hide", () => {
    assert.equal(formatBound(0), "0.0000");
    assert.equal(formatCount(0), "0");
  });
  it("counts are plain integers", () => {
    assert.equal(formatCount(3), "3");
    assert.equal(formatCount(5000), "5000");
    assert.equal(formatCount(null), "—");
  });
});

describe("ranks and field telemetry", () => {
  it("average-tie ranks render exactly", () => {
    assert.equal(formatRank(1), "1");
    assert.equal(formatRank(2.5), "2.5");
    assert.equal(formatRank(null), "—");
  });
  it("spearman renders value-only, no verdict", () => {
    assert.equal(formatSpearman(0.667168155), "0.667");
    assert.equal(formatSpearman(null), "—");
  });
  it("jaccard renders as a fraction, never a verdict", () => {
    assert.equal(formatJaccard(0.5), "0.500");
    assert.equal(formatJaccard(null), "—");
  });
  it("leader wording is neutral", () => {
    assert.equal(leaderWording(true), "LEADER MATCH");
    assert.equal(leaderWording(false), "LEADER DIFFERENT");
    assert.ok(!/good|bad|trust|reliable/i.test(leaderWording(true)));
    assert.ok(!/good|bad|trust|reliable/i.test(leaderWording(false)));
  });
});

describe("status labels", () => {
  it("every V3.9 status has a distinct text label", () => {
    const labels = new Set(
      [
        "AVAILABLE",
        "MISSING_SOURCE",
        "UNSUPPORTED_STATE",
        "NOT_APPLICABLE",
        "INSUFFICIENT_SIMULATIONS",
        "PROVENANCE_UNAVAILABLE",
      ].map(statusLabel),
    );
    assert.equal(labels.size, 6);
    assert.equal(statusLabel("PROVENANCE_UNAVAILABLE"), "Provenance unavailable");
  });
});
