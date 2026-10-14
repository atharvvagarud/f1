import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { selectedDriverFacts } from "./driverFacts.ts";

// Behavior tests for the Pit Wall selected-driver facts (V3.10C). Facts only:
// position, gaps, tyre, stint, pit stops from an already-loaded roster.
// Run with `node --test driverFacts.test.ts` (Node >= 22, no new dependencies).

type Driver = Parameters<typeof selectedDriverFacts>[0][number];

function driver(over: Partial<Driver> = {}): Driver {
  return {
    driver_id: "NOR",
    observable: true,
    observed_lap_number: 34,
    observed_time_s: 5023.1,
    observation_age_s: 0,
    position: 3,
    gap_to_leader_s: 4.231,
    gap_to_leader_valid: true,
    gap_to_leader_laps: null,
    gap_to_ahead_s: 1.105,
    gap_to_ahead_valid: true,
    gap_to_ahead_laps: null,
    compound: "medium",
    tyre_life: 12,
    fresh_tyre: false,
    stint_number: 2,
    stint_lap: 12,
    pit_stops_completed_so_far: 1,
    laps_since_last_pit_stop: 12,
    constructor_id: "mclaren",
    driver_number: 4,
    ...over,
  };
}

describe("selectedDriverFacts", () => {
  it("reports unselected with dashes and no driver", () => {
    const facts = selectedDriverFacts([driver()], null);
    assert.equal(facts.status, "unselected");
    assert.equal(facts.driverId, null);
    assert.equal(facts.position, "—");
  });

  it("reports position, gaps, tyre, stint, and pit stops for the selected driver", () => {
    const facts = selectedDriverFacts([driver()], "NOR");
    assert.equal(facts.status, "selected");
    assert.equal(facts.driverId, "NOR");
    assert.equal(facts.position, "P3");
    assert.equal(facts.gapToLeader, "+4.231");
    assert.equal(facts.gapToAhead, "+1.105");
    assert.equal(facts.tyre, "MEDIUM 12");
    assert.equal(facts.stint, "stint 2 · lap 12");
    assert.equal(facts.pitStops, "1");
  });

  it("reports no-evidence without switching identity", () => {
    const facts = selectedDriverFacts([driver({ driver_id: "VER" })], "NOR");
    assert.equal(facts.status, "no-evidence");
    assert.equal(facts.driverId, "NOR");
    assert.equal(facts.position, "—");
  });

  it("formats lapped gaps in laps and invalid gaps as n/a", () => {
    const lapped = selectedDriverFacts(
      [driver({ gap_to_leader_laps: 2, gap_to_leader_s: null })],
      "NOR",
    );
    assert.equal(lapped.gapToLeader, "+2 LAPS");
    const invalid = selectedDriverFacts(
      [driver({ gap_to_leader_valid: false, gap_to_leader_s: 9.9 })],
      "NOR",
    );
    assert.equal(invalid.gapToLeader, "n/a");
  });

  it("renders nulls as dashes, never zero", () => {
    const facts = selectedDriverFacts(
      [
        driver({
          position: null,
          gap_to_leader_s: null,
          compound: null,
          tyre_life: null,
          stint_number: null,
          pit_stops_completed_so_far: null,
        }),
      ],
      "NOR",
    );
    assert.equal(facts.status, "selected");
    assert.equal(facts.position, "—");
    assert.equal(facts.gapToLeader, "—");
    assert.equal(facts.tyre, "—");
    assert.equal(facts.stint, "—");
    assert.equal(facts.pitStops, "—");
  });

  it("marks fresh tyres without inventing numbers", () => {
    const facts = selectedDriverFacts(
      [driver({ compound: "soft", tyre_life: 0, fresh_tyre: true })],
      "NOR",
    );
    assert.equal(facts.tyre, "SOFT 0 · new");
  });

  it("carries no probabilities or simulated values", () => {
    const facts = selectedDriverFacts([driver()], "NOR");
    assert.deepEqual(Object.keys(facts).sort(), [
      "driverId",
      "gapToAhead",
      "gapToLeader",
      "pitStops",
      "position",
      "status",
      "stint",
      "tyre",
    ]);
  });
});
