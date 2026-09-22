import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  SIMULATION_COUNTS,
  DEFAULT_SIMULATION_COUNT,
  anchorFromFrame,
  anchorKey,
  clampFrameIndex,
  defaultFrameIndex,
  distributionLevel,
  distributionPositions,
  formatDistributionCell,
  formatExpectedFinish,
  formatPercent,
  mostFrequentWinner,
  isCurrentSimulationResponse,
  responseMatchesSelection,
  sortDriversByWin,
  sortDriversByExpectedFinish,
  unsupportedMessage,
  winMass,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./simulatorMachine.ts";
import type {
  ReplayFrameMeta,
  SimulationResponse,
} from "@/lib/v2";

// Pure simulator logic: exact-anchor mapping, result identity, stale-response
// guarding, deterministic ordering, verbatim probability rendering, and the
// factual unsupported-state message. No DOM, no network.

function frame(overrides: Partial<ReplayFrameMeta> = {}): ReplayFrameMeta {
  return {
    race_id: "2022-r01-R",
    frame_index: 12,
    anchor_driver_id: "perez",
    anchor_lap_number: 30,
    anchor_state_time_s: 6745.686,
    replay_contract_version: "v1",
    ...overrides,
  };
}

function response(overrides: Partial<SimulationResponse> = {}): SimulationResponse {
  return {
    race_id: "2022-r01-R",
    anchor_driver_id: "perez",
    anchor_lap_number: 30,
    anchor_state_time_s: 6745.686,
    simulation_contract_version: "v1",
    engine_version: "r4-engine-v1",
    monte_carlo_version: "r5-monte-carlo-v1",
    pit_dynamics_version: "r6-pit-dynamics-v1",
    mechanics: ["pit_dynamics"],
    probability_semantics: "MONTE_CARLO_FREQUENCY",
    probability_semantics_note: "note",
    parameter_set_id: "phase6-r3-empirical",
    parameter_version: "r3-v1.2024.4c2f85f08f1c",
    parameter_hash: "4c2f85f0",
    simulation_request_identity: "req",
    scientific_result_identity: "res",
    requested_simulation_count: 1000,
    valid_simulations: 1000,
    invalid_simulations: 0,
    master_seed: 20240101,
    engine_runtime_s: 1.0,
    runtime: {
      reconstruction_s: 0.04,
      adaptation_s: 0.001,
      simulation_s: 1.0,
      total_s: 1.05,
    },
    drivers: [
      {
        driver_id: "a",
        win_probability: 0.6,
        podium_probability: 0.9,
        expected_finish: 1.4,
        finish_position_distribution: [
          { position: 1, frequency: 0.6 },
          { position: 2, frequency: 0.4 },
        ],
        dnf_probability: null,
        points_probability: null,
        expected_points: null,
      },
      {
        driver_id: "b",
        win_probability: 0.4,
        podium_probability: 0.8,
        expected_finish: 1.9,
        finish_position_distribution: [
          { position: 1, frequency: 0.4 },
          { position: 2, frequency: 0.6 },
        ],
        dnf_probability: null,
        points_probability: null,
        expected_points: null,
      },
    ],
    ...overrides,
  };
}

describe("exact anchor mapping", () => {
  it("maps a replay frame to its exact four-part anchor", () => {
    const anchor = anchorFromFrame(frame());
    assert.deepEqual(anchor, {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
    });
  });
});

describe("frame selection bounds", () => {
  it("defaults to the middle frame", () => {
    assert.equal(defaultFrameIndex(0), 0);
    assert.equal(defaultFrameIndex(1), 0);
    assert.equal(defaultFrameIndex(101), 50);
  });

  it("clamps out-of-range and non-finite indices", () => {
    assert.equal(clampFrameIndex(-5, 10), 0);
    assert.equal(clampFrameIndex(999, 10), 9);
    assert.equal(clampFrameIndex(Number.NaN, 10), 0);
    assert.equal(clampFrameIndex(3, 0), 0);
  });
});

describe("result identity", () => {
  it("accepts a response for the exact selected anchor and count", () => {
    const anchor = anchorFromFrame(frame());
    assert.equal(responseMatchesSelection(response(), anchor, 1000), true);
  });

  it("rejects a response for a different state or count", () => {
    const anchor = anchorFromFrame(frame());
    assert.equal(
      responseMatchesSelection(response({ anchor_lap_number: 29 }), anchor, 1000),
      false,
    );
    assert.equal(responseMatchesSelection(response(), anchor, 10000), false);
    assert.equal(
      responseMatchesSelection(response({ race_id: "2021-r01-R" }), anchor, 1000),
      false,
    );
  });

  it("anchorKey is stable and count-sensitive", () => {
    const anchor = anchorFromFrame(frame());
    assert.equal(anchorKey(anchor, 1000), anchorKey(anchor, 1000));
    assert.notEqual(anchorKey(anchor, 1000), anchorKey(anchor, 10000));
  });
});

describe("stale-response protection", () => {
  it("accepts only the current session and request", () => {
    assert.equal(isCurrentSimulationResponse(5, 5, 2, 2), true);
    assert.equal(isCurrentSimulationResponse(4, 5, 2, 2), false);
    assert.equal(isCurrentSimulationResponse(5, 5, 1, 2), false);
  });
});

describe("deterministic ordering and verbatim probabilities", () => {
  it("sorts by win probability desc then driver id", () => {
    const ordered = sortDriversByWin([
      { ...response().drivers[1] },
      { ...response().drivers[0] },
    ]);
    assert.deepEqual(ordered.map((d) => d.driver_id), ["a", "b"]);
  });

  it("breaks ties deterministically by driver id", () => {
    const a = { ...response().drivers[0], driver_id: "z", win_probability: 0.5 };
    const b = { ...response().drivers[1], driver_id: "a", win_probability: 0.5 };
    const ordered = sortDriversByWin([a, b]);
    assert.deepEqual(ordered.map((d) => d.driver_id), ["a", "z"]);
  });

  it("win mass is the verbatim sum (never renormalized)", () => {
    const drivers = response().drivers;
    assert.equal(winMass(drivers), 1.0);
    // A valid Monte Carlo aggregate always sums to 1; the helper must not
    // scale it even when a synthetic payload does not.
    const odd = [{ ...drivers[0], win_probability: 0.3 }];
    assert.equal(winMass(odd), 0.3);
  });
});

describe("position distribution display", () => {
  it("most frequent winner is the deterministic win-order head", () => {
    assert.equal(mostFrequentWinner(response().drivers)?.driver_id, "a");
    assert.equal(mostFrequentWinner([]), null);
  });

  it("orders drivers by expected finish then id", () => {
    const ordered = sortDriversByExpectedFinish([
      { ...response().drivers[1], expected_finish: 5 },
      { ...response().drivers[0], expected_finish: 2 },
    ]);
    assert.deepEqual(ordered.map((d) => d.driver_id), ["a", "b"]);
  });

  it("collects only the actual positions, null last", () => {
    assert.deepEqual(distributionPositions(response().drivers), [1, 2]);
    const withNull = [
      {
        ...response().drivers[0],
        finish_position_distribution: [
          { position: 3, frequency: 0.5 },
          { position: null, frequency: 0.5 },
        ],
      },
    ];
    assert.deepEqual(distributionPositions(withNull), [3, null]);
    assert.deepEqual(distributionPositions([]), []);
  });

  it("maps frequency to a discrete intensity step without inventing data", () => {
    assert.equal(distributionLevel(0), 0);
    assert.equal(distributionLevel(-1), 0);
    assert.equal(distributionLevel(Number.NaN), 0);
    assert.equal(distributionLevel(0.01), 1);
    assert.equal(distributionLevel(0.1), 2);
    assert.equal(distributionLevel(0.5), 3);
  });

  it("formats the matrix cell as text, blank only at exactly zero", () => {
    assert.equal(formatDistributionCell(0), "");
    assert.equal(formatDistributionCell(0.123), "12.3");
    assert.equal(formatDistributionCell(0.0002), "<0.1");
    assert.equal(formatDistributionCell(Number.NaN), "");
  });
});

describe("rendering", () => {  it("formats probabilities as percent and null stays placeholder", () => {
    assert.equal(formatPercent(0.123), "12.3%");
    assert.equal(formatPercent(1), "100.0%");
    assert.equal(formatPercent(null), "—");
  });

  it("formats expected finish and null", () => {
    assert.equal(formatExpectedFinish(2.199), "2.20");
    assert.equal(formatExpectedFinish(null), "—");
  });

  it("exposes bounded synchronous count options", () => {
    assert.deepEqual([...SIMULATION_COUNTS], [1000, 10000]);
    assert.equal(DEFAULT_SIMULATION_COUNT, 1000);
  });
});

describe("unsupported-state message", () => {
  it("uses the factual contemporaneity wording and never claims retirement", () => {
    const message = unsupportedMessage({
      error: "simulation_unsupported",
      reason: "non_contemporaneous_roster_member",
      detail: "giovinazzi age=1556.3s",
    });
    assert.match(message, /cannot be simulated safely/);
    assert.doesNotMatch(message, /retire/i);
    assert.doesNotMatch(message, /giovinazzi/);
  });

  it("names the reason for other unsupported states", () => {
    const message = unsupportedMessage({
      error: "simulation_unsupported",
      reason: "wet_compound_state",
      detail: "driver is on WET",
    });
    assert.match(message, /wet_compound_state/);
  });
});
