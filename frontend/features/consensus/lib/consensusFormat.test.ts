// Pure display-transform tests (V3.8G). Run with:
// node --test features/consensus/lib/consensusFormat.test.ts
import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { compareFieldRows, formatDisplacement, formatGapPp, formatLeaders, formatPct, formatRank, refusalCopy } from "./consensusFormat.ts";

describe("formatPct", () => {
  it("scales native*100 with one decimal", () => {
    assert.equal(formatPct(0.8088), "80.9%");
    assert.equal(formatPct(0), "0.0%");
  });
  it("null stays null (unavailable is not zero)", () => {
    assert.equal(formatPct(null), null);
  });
});

describe("formatGapPp", () => {
  it("signs simulation-minus-model explicitly", () => {
    assert.equal(formatGapPp(0.8088), "+80.9 pp");
    assert.equal(formatGapPp(-0.001), "\u22120.1 pp");
    assert.equal(formatGapPp(0), "0.0 pp");
    assert.equal(formatGapPp(null), null);
  });
});

describe("formatRank", () => {
  it("renders average ties exactly", () => {
    assert.equal(formatRank(1), "1");
    assert.equal(formatRank(2.5), "2.5");
    assert.equal(formatRank(null), "\u2014");
  });
});

describe("formatDisplacement", () => {
  it("preserves sign (sim minus model)", () => {
    assert.equal(formatDisplacement(-1), "\u22121");
    assert.equal(formatDisplacement(2), "+2");
    assert.equal(formatDisplacement(0), "0");
  });
});

describe("formatLeaders", () => {
  it("names every tied leader", () => {
    assert.equal(formatLeaders(["hamilton"]), "HAMILTON");
    assert.equal(formatLeaders(["a", "b"]), "A · B");
    assert.equal(formatLeaders([]), "\u2014");
  });
});

describe("refusalCopy", () => {
  it("explains typed reasons without internals", () => {
    assert.match(refusalCopy("MC2_STATE_INELIGIBLE"), /Missing is not zero/);
    assert.match(refusalCopy("STATE_NOT_AVAILABLE"), /outside product support/);
  });
});

describe("compareFieldRows", () => {
  const a = { driver_id: "b", p_model: 0.2, p_simulation: 0.8, absolute_gap: 0.6 };
  const b = { driver_id: "a", p_model: 0.5, p_simulation: 0.1, absolute_gap: 0.4 };
  it("sorts by key and direction", () => {
    assert.equal(compareFieldRows(a, b, "driver", 1) > 0, true);
    assert.equal(compareFieldRows(a, b, "gap", -1) < 0, true);
    assert.equal(compareFieldRows(a, b, "model", 1) < 0, true);
  });
});
