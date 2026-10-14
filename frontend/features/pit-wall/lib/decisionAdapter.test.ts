// Exact workspace -> decision-product adapter tests (V3.10G).
//
// Exact, deterministic, causal, fail-closed: no nearest-state snapping,
// no substitution, no probing. Unsupported stays unsupported.
// Run with `node --test decisionAdapter.test.ts`.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { adaptDecisionTarget, eligibleNDomain, matchStrategyEntry, seasonOfRaceId, validateIntervention } from "./decisionAdapter.ts";

const FRAME = {
  raceId: "2022-r01-R",
  frameIndex: 583,
  anchorDriverId: "perez",
  anchorLapNumber: 30,
  anchorStateTimeS: 6745.686,
};

describe("season firewall", () => {
  it("parses the leading season", () => {
    assert.equal(seasonOfRaceId("2022-r01-R"), 2022);
    assert.equal(seasonOfRaceId("2018-r11-R"), 2018);
    assert.equal(seasonOfRaceId("2025-r01-R"), 2025);
  });

  it("refuses unparseable race identity", () => {
    assert.equal(seasonOfRaceId(""), null);
    assert.equal(seasonOfRaceId("not-a-race"), null);
  });

  it("refuses any 2025 race without issuing work", () => {
    const result = adaptDecisionTarget({ ...FRAME, raceId: "2025-r01-R" }, "perez");
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.refusal.code, "SEASON_UNSUPPORTED");
  });

  it("refuses pre-2018 races", () => {
    const result = adaptDecisionTarget({ ...FRAME, raceId: "2017-r01-R" }, "perez");
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.refusal.code, "SEASON_UNSUPPORTED");
  });
});

describe("exact identity mapping", () => {
  it("maps race + exact anchor + selected driver verbatim", () => {
    const result = adaptDecisionTarget(FRAME, "perez");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.deepEqual(result.anchor, {
        race_id: "2022-r01-R",
        anchor_driver_id: "perez",
        anchor_lap_number: 30,
        anchor_state_time_s: 6745.686,
      });
      assert.equal(result.targetDriverId, "perez");
    }
  });

  it("target may differ from the anchor driver (exact, no substitution)", () => {
    const result = adaptDecisionTarget(FRAME, "leclerc");
    assert.equal(result.ok, true);
    if (result.ok) {
      assert.equal(result.anchor.anchor_driver_id, "perez");
      assert.equal(result.targetDriverId, "leclerc");
    }
  });

  it("missing frame is refused, never snapped", () => {
    const result = adaptDecisionTarget(null, "perez");
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.refusal.code, "NO_FRAME");
  });

  it("missing driver is refused, never defaulted", () => {
    for (const driver of [null, "", "  "]) {
      const result = adaptDecisionTarget(FRAME, driver);
      assert.equal(result.ok, false);
      if (!result.ok) assert.equal(result.refusal.code, "NO_DRIVER");
    }
  });

  it("malformed anchors are refused, never repaired", () => {
    assert.equal(
      adaptDecisionTarget({ ...FRAME, anchorLapNumber: 0 }, "perez").ok,
      false,
    );
    assert.equal(
      adaptDecisionTarget({ ...FRAME, anchorStateTimeS: NaN }, "perez").ok,
      false,
    );
    assert.equal(
      adaptDecisionTarget({ ...FRAME, anchorDriverId: "" }, "perez").ok,
      false,
    );
  });
});

describe("strategy catalogue matching", () => {
  const entry = {
    race_id: "2022-r01-R",
    anchor_driver_id: "perez",
    anchor_lap_number: 30,
    anchor_state_time_s: 6745.686,
    target_driver_id: "perez",
    master_seed: 20240101,
    simulation_count: 5000,
    supported: true,
    alternative_count: 9,
    comparison_identities: [],
    cache_key: "k",
  };

  it("matches the exact race + anchor + target", () => {
    const hit = matchStrategyEntry([entry], {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
    }, "perez");
    assert.equal(hit, entry);
  });

  it("rejects near misses: no nearest-state snapping", () => {
    const anchor = {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
    };
    // Same lap, different state time.
    assert.equal(
      matchStrategyEntry([entry], { ...anchor, anchor_state_time_s: 6745.0 }, "perez"),
      null,
    );
    // Same state, different target driver.
    assert.equal(matchStrategyEntry([entry], anchor, "leclerc"), null);
    // Same anchor, different race.
    assert.equal(
      matchStrategyEntry([entry], { ...anchor, race_id: "2022-r02-R" }, "perez"),
      null,
    );
    // Empty catalogue.
    assert.equal(matchStrategyEntry([], anchor, "perez"), null);
  });

  it("unsupported exact state remains unsupported (missing is not zero)", () => {
    const hit = matchStrategyEntry([entry], {
      race_id: "2022-r01-R",
      anchor_driver_id: "leclerc",
      anchor_lap_number: 1,
      anchor_state_time_s: 3854.174,
    }, "leclerc");
    assert.equal(hit, null);
  });
});

describe("counterfactual intervention domain", () => {
  const drivers = [
    { driver_id: "perez", position: 4, decision_lap: 29, remaining_laps: 28, eligible_n_min: 1, eligible_n_max: 27, eligible: true, compound: "MEDIUM", status: "ACTIVE" },
    { driver_id: "norris", position: null, decision_lap: 29, remaining_laps: 0, eligible_n_min: null, eligible_n_max: null, eligible: false, compound: null, status: "RETIRED" },
  ];

  it("reads the eligible N domain verbatim", () => {
    assert.deepEqual(eligibleNDomain(drivers, "perez"), { min: 1, max: 27, decisionLap: 29 });
  });

  it("ineligible and absent drivers yield no domain", () => {
    assert.equal(eligibleNDomain(drivers, "norris"), null);
    assert.equal(eligibleNDomain(drivers, "alonso"), null);
  });

  it("accepts in-domain interventions", () => {
    const domain = eligibleNDomain(drivers, "perez");
    assert.deepEqual(
      validateIntervention(1, domain, "MEDIUM", ["SOFT", "MEDIUM", "HARD", "SAMPLED"]),
      { ok: true },
    );
  });

  it("rejects out-of-domain N without clamping or rescheduling", () => {
    const domain = eligibleNDomain(drivers, "perez");
    for (const n of [0, 28, 99]) {
      const result = validateIntervention(n, domain, "MEDIUM", ["SOFT", "MEDIUM", "HARD", "SAMPLED"]);
      assert.equal(result.ok, false);
    }
    // No domain at all is rejected, never defaulted.
    assert.equal(validateIntervention(1, null, "MEDIUM", ["MEDIUM"]).ok, false);
  });

  it("rejects unsupported compounds", () => {
    const domain = eligibleNDomain(drivers, "perez");
    assert.equal(validateIntervention(1, domain, "WET", ["SOFT", "MEDIUM", "HARD", "SAMPLED"]).ok, false);
  });
});
