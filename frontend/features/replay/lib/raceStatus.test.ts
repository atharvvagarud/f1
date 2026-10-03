import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { raceControlMessageOf, raceStatusOf } from "./raceStatus.ts";

// Contract tests for the P12-8 race-status view-model: frozen D9 token
// vocabulary, null-safe UNKNOWN, deterministic message filtering.
// Run with `node --test features/replay/lib/raceStatus.test.ts`.

function rc(over: Record<string, string | null> = {}) {
  return {
    track_state: "all_clear",
    last_message_category: null,
    last_message_flag: null,
    ...over,
  };
}

describe("track-status vocabulary", () => {
  it("maps every frozen D9 token, never leaking codes", () => {
    assert.equal(raceStatusOf(rc({ track_state: "all_clear" })).label, "GREEN");
    assert.equal(raceStatusOf(rc({ track_state: "yellow" })).label, "YELLOW");
    assert.equal(
      raceStatusOf(rc({ track_state: "safety_car" })).label,
      "SAFETY CAR",
    );
    assert.equal(raceStatusOf(rc({ track_state: "vsc" })).label, "VIRTUAL SC");
    assert.equal(
      raceStatusOf(rc({ track_state: "vsc_ending" })).label,
      "VIRTUAL SC",
    );
    assert.equal(
      raceStatusOf(rc({ track_state: "red_flag" })).label,
      "RED FLAG",
    );
  });

  it("renders null/unknown as explicit UNKNOWN, never blank", () => {
    assert.equal(raceStatusOf(rc({ track_state: null })).key, "unknown");
    assert.equal(raceStatusOf(rc({ track_state: null })).label, "STATUS UNKNOWN");
    assert.equal(raceStatusOf(rc({ track_state: "bogus" })).key, "unknown");
    assert.equal(raceStatusOf(null).key, "unknown");
  });

  it("always carries a text label (never colour-only)", () => {
    for (const token of [
      "all_clear",
      "yellow",
      "safety_car",
      "vsc",
      "vsc_ending",
      "red_flag",
      null,
    ]) {
      const view = raceStatusOf(rc({ track_state: token }));
      assert.ok(view.label.length > 0);
      assert.ok(view.chipClassName.length > 0);
    }
  });
});

describe("race-control message filter", () => {
  it("shows status-relevant Flag messages verbatim", () => {
    assert.deepEqual(
      raceControlMessageOf(
        rc({ last_message_category: "Flag", last_message_flag: "YELLOW" }),
      ),
      { category: "Flag", flag: "YELLOW" },
    );
    assert.deepEqual(
      raceControlMessageOf(
        rc({ last_message_category: "Flag", last_message_flag: "DOUBLE YELLOW" }),
      ),
      { category: "Flag", flag: "DOUBLE YELLOW" },
    );
    assert.deepEqual(
      raceControlMessageOf(
        rc({ last_message_category: "Flag", last_message_flag: "RED" }),
      ),
      { category: "Flag", flag: "RED" },
    );
  });

  it("hides notice/noise flags and chatter categories", () => {
    for (const flag of ["BLUE", "CLEAR", "GREEN", "CHEQUERED", "BLACK AND WHITE", null]) {
      assert.equal(
        raceControlMessageOf(
          rc({ last_message_category: "Flag", last_message_flag: flag }),
        ),
        null,
      );
    }
    for (const category of ["Drs", "CarEvent", "Other", null]) {
      assert.equal(
        raceControlMessageOf(
          rc({ last_message_category: category, last_message_flag: "YELLOW" }),
        ),
        null,
      );
    }
    // A SafetyCar-category message naming a status flag is status-relevant
    // (empirically SafetyCar flags are always null, so this arm is idle).
    assert.deepEqual(
      raceControlMessageOf(
        rc({ last_message_category: "SafetyCar", last_message_flag: "YELLOW" }),
      ),
      { category: "SafetyCar", flag: "YELLOW" },
    );
    assert.equal(
      raceControlMessageOf(
        rc({ last_message_category: "SafetyCar", last_message_flag: null }),
      ),
      null,
    );
    assert.equal(raceControlMessageOf(null), null);
  });
});
