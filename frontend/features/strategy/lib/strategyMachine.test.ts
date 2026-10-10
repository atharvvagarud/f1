import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import {
  CANONICAL_CANDIDATES,
  DEFAULT_CANDIDATE_KEYS,
  DEFAULT_STRATEGY_COUNT,
  DEFAULT_STRATEGY_OBJECTIVE,
  FORBIDDEN_STRATEGY_COPY,
  MAX_CANDIDATES_AT_10K,
  STRATEGY_COUNTS,
  canAddCandidate,
  candidateKey,
  clampStrategyFrameIndex,
  defaultStrategyFrameIndex,
  formatDeltaPoints,
  formatDeltaPositions,
  formatFinish,
  formatProbability,
  formatSamplingInterval,
  isCurrentStrategyResponse,
  specsForKeys,
  strategyAnchorFromFrame,
  strategyRequestKey,
  strategyResponseMatchesSelection,
  strategyUnsupportedMessage,
  workloadBand,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./strategyMachine.ts";

// Strategy pure logic (strategyMachine.ts): canonical candidate catalog,
// neutral defaults, workload bands, identity guards, and unit formatting.
// Probability deltas are percentage points; finish deltas are positions with
// positive = estimated improvement.

describe("strategy candidate catalog", () => {
  it("exposes exactly the canonical 9 in canonical order", () => {
    assert.equal(CANONICAL_CANDIDATES.length, 9);
    assert.deepEqual(
      CANONICAL_CANDIDATES.map((c) => c.key),
      [
        "STAY_OUT:SAMPLED",
        "PIT_NOW:SAMPLED",
        "PIT_NOW:SOFT",
        "PIT_NOW:MEDIUM",
        "PIT_NOW:HARD",
        "PIT_NEXT_LAP:SAMPLED",
        "PIT_NEXT_LAP:SOFT",
        "PIT_NEXT_LAP:MEDIUM",
        "PIT_NEXT_LAP:HARD",
      ],
    );
  });

  it("default selection has at most 4 neutral candidates", () => {
    assert.ok(DEFAULT_CANDIDATE_KEYS.length <= 4);
    assert.ok(DEFAULT_CANDIDATE_KEYS.includes("STAY_OUT:SAMPLED"));
    assert.ok(DEFAULT_CANDIDATE_KEYS.includes("PIT_NOW:SAMPLED"));
    assert.ok(DEFAULT_CANDIDATE_KEYS.includes("PIT_NEXT_LAP:SAMPLED"));
    for (const key of DEFAULT_CANDIDATE_KEYS) {
      assert.ok(
        CANONICAL_CANDIDATES.some((c) => c.key === key),
        `default key is canonical: ${key}`,
      );
    }
  });

  it("candidateKey distinguishes sampled from explicit compounds", () => {
    assert.equal(
      candidateKey({ action: "PIT_NOW", requested_compound: null }),
      "PIT_NOW:SAMPLED",
    );
    assert.equal(
      candidateKey({ action: "PIT_NOW", requested_compound: "SOFT" }),
      "PIT_NOW:SOFT",
    );
  });

  it("specsForKeys round-trips the default set and rejects unknowns", () => {
    const specs = specsForKeys(DEFAULT_CANDIDATE_KEYS);
    assert.equal(specs.length, DEFAULT_CANDIDATE_KEYS.length);
    assert.throws(() => specsForKeys(["TELEPORT:SAMPLED"]), /Unknown/);
  });
});

describe("strategy defaults and bounds", () => {
  it("defaults to 1000 trials and an explicit visible objective", () => {
    assert.equal(DEFAULT_STRATEGY_COUNT, 1000);
    assert.deepEqual([...STRATEGY_COUNTS], [1000, 10000]);
    assert.equal(DEFAULT_STRATEGY_OBJECTIVE, "MAXIMIZE_WIN_PROBABILITY");
  });

  it("caps 10k comparisons at 3 candidates", () => {
    assert.equal(MAX_CANDIDATES_AT_10K, 3);
    assert.equal(canAddCandidate(1000, ["a", "b", "c", "d"]), true);
    assert.equal(canAddCandidate(10000, ["a", "b"]), true);
    assert.equal(canAddCandidate(10000, ["a", "b", "c"]), false);
  });

  it("classifies workload bands from S6 evidence", () => {
    assert.equal(workloadBand(1000, 4), "STANDARD");
    assert.equal(workloadBand(1000, 9), "HEAVY");
    assert.equal(workloadBand(10000, 1), "VERY_HEAVY");
    assert.equal(workloadBand(10000, 3), "VERY_HEAVY");
  });
});

describe("strategy identity guards", () => {
  const frame = {
    race_id: "2022-r01-R",
    frame_index: 4,
    anchor_driver_id: "perez",
    anchor_lap_number: 30,
    anchor_state_time_s: 6745.686,
    replay_contract_version: "v1",
  };

  it("maps a frame to its exact anchor without re-derivation", () => {
    assert.deepEqual(strategyAnchorFromFrame(frame), {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
    });
  });

  it("binds a result to the full request identity", () => {
    const anchor = strategyAnchorFromFrame(frame);
    const base = {
      anchor,
      target: "perez",
      objective: "MAXIMIZE_WIN_PROBABILITY" as const,
      count: 1000,
      seed: undefined,
      candidateKeys: ["STAY_OUT:SAMPLED"],
    };
    const key = strategyRequestKey(base);
    assert.notEqual(
      key,
      strategyRequestKey({ ...base, target: "leclerc" }),
    );
    assert.notEqual(
      key,
      strategyRequestKey({
        ...base,
        objective: "MINIMIZE_EXPECTED_FINISH" as const,
      }),
    );
    assert.notEqual(
      key,
      strategyRequestKey({ ...base, candidateKeys: ["PIT_NOW:SAMPLED"] }),
    );
    // Candidate order is normalized: same set, same identity.
    assert.equal(
      key,
      strategyRequestKey({
        ...base,
        candidateKeys: ["STAY_OUT:SAMPLED"],
      }),
    );
  });

  it("accepts only responses matching the exact selection", () => {
    const anchor = strategyAnchorFromFrame(frame);
    const response = {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
      target_driver_id: "perez",
      objective: "MAXIMIZE_WIN_PROBABILITY",
      simulation_count: 1000,
    };
    assert.equal(
      strategyResponseMatchesSelection(
        // deno-lint-ignore no-explicit-any
        response as never,
        anchor,
        "perez",
        "MAXIMIZE_WIN_PROBABILITY",
        1000,
      ),
      true,
    );
    assert.equal(
      strategyResponseMatchesSelection(
        // deno-lint-ignore no-explicit-any
        response as never,
        anchor,
        "leclerc",
        "MAXIMIZE_WIN_PROBABILITY",
        1000,
      ),
      false,
    );
    assert.equal(
      strategyResponseMatchesSelection(
        // deno-lint-ignore no-explicit-any
        { ...response, simulation_count: 10000 } as never,
        anchor,
        "perez",
        "MAXIMIZE_WIN_PROBABILITY",
        1000,
      ),
      false,
    );
  });

  it("rejects stale responses by session and request id", () => {
    assert.equal(isCurrentStrategyResponse(2, 2, 1, 1), true);
    assert.equal(isCurrentStrategyResponse(1, 2, 1, 1), false);
    assert.equal(isCurrentStrategyResponse(2, 2, 1, 2), false);
  });

  it("clamps frame navigation without inventing states", () => {
    assert.equal(defaultStrategyFrameIndex(0), 0);
    assert.equal(defaultStrategyFrameIndex(11), 5);
    assert.equal(clampStrategyFrameIndex(99, 11), 10);
    assert.equal(clampStrategyFrameIndex(-3, 11), 0);
  });
});

describe("strategy formatting", () => {
  it("renders probabilities as percent and deltas as points", () => {
    assert.equal(formatProbability(0.612), "61.2%");
    assert.equal(formatProbability(null), "—");
    // Deltas are percentage points, never confused with probability.
    assert.equal(formatDeltaPoints(0.024), "+2.4 pp");
    assert.equal(formatDeltaPoints(-0.031), "−3.1 pp");
    assert.equal(formatDeltaPoints(null), "—");
  });

  it("renders expected finish in positions with frozen sign", () => {
    assert.equal(formatFinish(7.456), "7.46");
    // Positive = estimated improvement (baseline minus candidate).
    assert.equal(formatDeltaPositions(1.2), "+1.20 pos");
    assert.equal(formatDeltaPositions(-0.5), "−0.50 pos");
    assert.equal(formatDeltaPositions(null), "—");
  });

  it("renders sampling intervals in the metric unit", () => {
    assert.equal(
      formatSamplingInterval(0.008, 0.041, false),
      "+0.8 pp to +4.1 pp",
    );
    assert.equal(
      formatSamplingInterval(0.5, 1.5, true),
      "+0.50 pos to +1.50 pos",
    );
    assert.equal(formatSamplingInterval(null, 0.1, false), "interval withheld");
  });

  it("explains unsupported states without inventing outcomes", () => {
    assert.match(
      strategyUnsupportedMessage({
        reason: "non_contemporaneous_roster_member",
      }),
      /contemporaneously/,
    );
    assert.match(
      strategyUnsupportedMessage({ reason: "target_driver_not_in_roster" }),
      /not in the contemporaneous roster/,
    );
  });
});

describe("strategy product copy", () => {
  it("contains no recommendation language in shipped surfaces", () => {
    const here = dirname(new URL(import.meta.url).pathname);
    const sources = [
      join(here, "strategyMachine.ts"),
      join(here, "strategy2Machine.ts"),
      join(here, "..", "components", "Strategy2View.tsx"),
      join(here, "..", "components", "Strategy2Results.tsx"),
      join(here, "..", "hooks", "useStrategy2.ts"),
    ];
    for (const path of sources) {
      const raw = readFileSync(path, "utf8");
      // The audited list itself names the forbidden phrases; exclude its
      // definition so the audit checks shipped copy, not the audit.
      const text = raw
        .replace(/export const FORBIDDEN_STRATEGY_COPY[\s\S]*?\];/, "")
        .replace(/export const STRATEGY2_FORBIDDEN_COPY[\s\S]*?\];/, "")
        .toLowerCase();
      for (const phrase of FORBIDDEN_STRATEGY_COPY) {
        assert.ok(
          !text.includes(phrase),
          `${path} contains forbidden copy: ${phrase}`,
        );
      }
    }
  });
});
