// Compact decision-exploration display tests (V3.10G).
//
// Canonical order preserved, frozen delta orientation intact, no ranking,
// no recommendation, no qualitative thresholds. Source-scan neutrality
// follows the frozen expert-surface precedent.
// Run with `node --test decisionDisplay.test.ts`.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { canonicalAlternativeOrder, counterfactualCompactLines, DECISION_FORBIDDEN_COPY, strategyCompactLines } from "./decisionDisplay.ts";

const HERE = dirname(fileURLToPath(import.meta.url));

function strategyAlternative(over: Record<string, unknown> = {}) {
  return {
    candidate_key: "PIT_NOW:MEDIUM",
    candidate_identity: "id",
    action: "PIT_NOW",
    requested_compound: "MEDIUM",
    evaluated: true,
    reason: null,
    reference_aggregate: null,
    alternative_aggregate: null,
    deltas: [
      { metric: "delta_win_frequency", point_estimate: -0.1618, paired_se: 0.008, ci_low: -0.177, ci_high: -0.146, availability: "AVAILABLE", valid_pairs: 5000, uncertainty_semantics: "", interval_label: "" },
      { metric: "delta_podium_frequency", point_estimate: -0.1356, paired_se: 0.008, ci_low: -0.151, ci_high: -0.12, availability: "AVAILABLE", valid_pairs: 5000, uncertainty_semantics: "", interval_label: "" },
      { metric: "delta_expected_finish", point_estimate: -0.6142, paired_se: 0.026, ci_low: -0.666, ci_high: -0.562, availability: "AVAILABLE", valid_pairs: 5000, uncertainty_semantics: "", interval_label: "" },
    ],
    execution: null,
    requested_pairs: 5000,
    complete_pairs: 5000,
    excluded_pairs: 0,
    comparison_key: null,
    comparison_identity: null,
    ...over,
  };
}

describe("canonical order", () => {
  it("alternative order is the frozen canonical grid, never performance-sorted", () => {
    assert.deepEqual(canonicalAlternativeOrder(), [
      "STAY_OUT:SAMPLED",
      "PIT_NOW:SAMPLED",
      "PIT_NOW:SOFT",
      "PIT_NOW:MEDIUM",
      "PIT_NOW:HARD",
      "PIT_NEXT_LAP:SAMPLED",
      "PIT_NEXT_LAP:SOFT",
      "PIT_NEXT_LAP:MEDIUM",
      "PIT_NEXT_LAP:HARD",
    ]);
  });
});

describe("strategy compact lines", () => {
  it("shows WIN / PODIUM / EXPECTED FINISH with frozen signs", () => {
    const lines = strategyCompactLines(strategyAlternative());
    assert.deepEqual(lines.map((l) => l.short), ["Δ WIN", "Δ PODIUM", "Δ EXPECTED FINISH"]);
    // ALT − REF probability deltas pass through verbatim (negative stays negative).
    assert.ok(lines[0].point.includes("16.2"), `win point: ${lines[0].point}`);
    assert.ok(lines[0].point.trim().startsWith("−"), `win sign: ${lines[0].point}`);
    // Expected finish REF − ALT positive = improvement; negative passes through.
    assert.ok(lines[2].point.trim().startsWith("−"), `exp sign: ${lines[2].point}`);
  });

  it("intervals render as sampling ranges, never confidence claims", () => {
    const lines = strategyCompactLines(strategyAlternative());
    for (const line of lines) {
      assert.ok(line.interval.includes("to"), `interval: ${line.interval}`);
    }
  });

  it("withheld deltas render as em-dash, never zero", () => {
    const lines = strategyCompactLines(strategyAlternative({ deltas: [] }));
    assert.ok(lines.every((l) => l.point === "—"));
  });
});

describe("counterfactual compact lines", () => {
  const response = {
    deltas: {
      delta_win_frequency: { metric: "delta_win_frequency", point_estimate: -0.1618, paired_se: 0.008, ci_low: -0.177, ci_high: -0.146 },
      delta_podium_frequency: { metric: "delta_podium_frequency", point_estimate: -0.1356, paired_se: 0.008, ci_low: -0.151, ci_high: -0.12 },
      delta_top5_frequency: { metric: "delta_top5_frequency", point_estimate: -0.03, paired_se: 0.005, ci_low: -0.04, ci_high: -0.02 },
      delta_expected_finish: { metric: "delta_expected_finish", point_estimate: -0.6142, paired_se: 0.026, ci_low: -0.666, ci_high: -0.562 },
      delta_position_gain_loss: { metric: "delta_position_gain_loss", point_estimate: -0.6142, paired_se: null, ci_low: null, ci_high: null },
    },
    // Partial payload: the compact selector reads deltas only (never
    // recomputes aggregates). Structural parity against full expert
    // payloads is validated live in results/v3/v3_10g/*parity*.json.
  } as unknown as import("../../../lib/v2.ts").CounterfactualCompareResponse;

  it("preserves frozen metric order and verbatim orientation", () => {
    const lines = counterfactualCompactLines(response);
    assert.deepEqual(lines.map((l) => l.short), ["WIN", "POD", "TOP5", "EXP", "GAIN"]);
    assert.ok(lines[0].point.includes("16.2"), `cf win: ${lines[0].point}`);
  });
});

describe("neutrality", () => {
  it("forbidden list covers ranking, advice, and alternate-history framing", () => {
    for (const phrase of ["best strategy", "optimal", "should pit", "alternate history", "real-world confidence", "advantage score"]) {
      assert.ok(
        DECISION_FORBIDDEN_COPY.includes(phrase),
        `forbidden list must contain: ${phrase}`,
      );
    }
  });

  it("DecisionExploration surface contains no forbidden copy", () => {
    const raw = readFileSync(join(HERE, "..", "components", "DecisionExploration.tsx"), "utf8").toLowerCase();
    for (const line of raw.split("\n")) {
      if (/forbidden_copy|doesnotmatch|assert\.ok\(!|never ranked|no .* language/i.test(line)) continue;
      for (const phrase of DECISION_FORBIDDEN_COPY) {
        assert.doesNotMatch(line, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), `forbidden phrase in DecisionExploration: ${phrase}`);
      }
    }
  });
});
