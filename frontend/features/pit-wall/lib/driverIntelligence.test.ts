import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { selectDriverIntelligence } from "./driverIntelligence.ts";
import type { UncertaintyCompare, UncertaintyDriver } from "../../uncertainty/lib/uncertaintyClient.ts";

// Selected-driver intelligence slice (V3.10E). Verbatim selection over a
// frozen compare bundle: values pass through, absent drivers yield null
// (never a substitute), missing arms stay null (never zero).
// Run with `node --test driverIntelligence.test.ts`.

function driver(over: Partial<UncertaintyDriver> = {}): UncertaintyDriver {
  return {
    driver_id: "NOR",
    status: "AVAILABLE",
    missing_arm: null,
    disagreement: {
      status: "AVAILABLE",
      p_model: 0.312,
      p_model_family: "INDEPENDENT_BINARY",
      p_simulation: 0.287,
      p_simulation_family: "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY",
      signed_gap: -0.025,
      absolute_gap: 0.025,
      model_rank: 2,
      simulation_rank: 3,
      model_inside_simulation_wilson: true,
    },
    monte_carlo_sampling: {
      status: "AVAILABLE",
      success_count_k: 1435,
      valid_futures_n: 5000,
      p_hat: 0.287,
      standard_error: 0.0064,
      wilson_95_lower: 0.2746,
      wilson_95_upper: 0.2998,
      precision_label: "FINITE_MC_SAMPLING_CONTEXT_ONLY",
    },
    diagnostic: null,
    ...over,
  };
}

function bundle(drivers: UncertaintyDriver[]): UncertaintyCompare {
  return {
    schema_version: "v3.9c",
    metric_implementation: "v3.9b",
    state: {
      state_id: "2024-r21-R:2",
      race_id: "2024-r21-R",
      lap_number: 2,
      state_time_s: 4491.366,
      stage: null,
      season: 2024,
    },
    sources: {
      model: { source: "logistic", probability_family: "INDEPENDENT_BINARY" },
      simulation: {
        source: "mc2-e",
        probability_family: "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY",
      },
    },
    drivers,
    field: {
      n_common_drivers: 20,
      rank_correlation_spearman: 0.91,
      leader_model: "VER",
      leader_simulation: "VER",
      leader_agree: true,
      top3_jaccard: 0.5,
    },
    simulator_sensitivity: {
      status: "NOT_ESTABLISHED",
      executable: false,
      reason: "no perturbation range registered",
      gate: "u3",
      gate_version: "v1",
    },
    availability: {
      race_id: "2024-r21-R",
      anchor_lap_number: 2,
      anchor_state_time_s: 4491.366,
      model: "AVAILABLE",
      model_reason: null,
      simulation: "AVAILABLE",
      simulation_reason: null,
      comparison: "COMPARABLE",
      simulator_sensitivity: "NOT_ESTABLISHED",
    },
    provenance: { bundle: "v3.9c-test" },
  };
}

describe("selectDriverIntelligence", () => {
  it("returns verbatim driver evidence plus bundle context", () => {
    const slice = selectDriverIntelligence(bundle([driver()]), "NOR");
    assert.ok(slice.driver);
    assert.equal(slice.driver.pModel, 0.312);
    assert.equal(slice.driver.pSimulation, 0.287);
    assert.equal(slice.driver.signedGap, -0.025);
    assert.equal(slice.driver.modelRank, 2);
    assert.equal(slice.driver.simulationRank, 3);
    assert.equal(slice.driver.modelInsideWilson, true);
    assert.equal(slice.driver.sampling?.validFuturesN, 5000);
    assert.equal(slice.driver.sampling?.wilsonLower, 0.2746);
    assert.equal(slice.bundle.leaderAgree, true);
    assert.equal(slice.bundle.modelFamily, "INDEPENDENT_BINARY");
    assert.equal(
      slice.bundle.simulationFamily,
      "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY",
    );
    assert.equal(slice.bundle.sensitivityStatus, "NOT_ESTABLISHED");
  });

  it("returns null driver without substitution when the row is absent", () => {
    const slice = selectDriverIntelligence(
      bundle([driver({ driver_id: "VER" })]),
      "NOR",
    );
    assert.equal(slice.driver, null);
    assert.equal(slice.bundle.nCommon, 20);
  });

  it("passes missing arms through as null, never zero", () => {
    const slice = selectDriverIntelligence(
      bundle([
        driver({
          status: "MISSING_SOURCE",
          missing_arm: "simulation",
          disagreement: null,
          monte_carlo_sampling: null,
        }),
      ]),
      "NOR",
    );
    assert.ok(slice.driver);
    assert.equal(slice.driver.status, "MISSING_SOURCE");
    assert.equal(slice.driver.missingArm, "simulation");
    assert.equal(slice.driver.pModel, null);
    assert.equal(slice.driver.pSimulation, null);
    assert.equal(slice.driver.sampling, null);
  });

  it("keeps disagreement without sampling (and vice versa)", () => {
    const noSampling = selectDriverIntelligence(
      bundle([driver({ monte_carlo_sampling: null })]),
      "NOR",
    );
    assert.ok(noSampling.driver);
    assert.equal(noSampling.driver.pModel, 0.312);
    assert.equal(noSampling.driver.sampling, null);
  });

  it("carries field disagreement and sensitivity verbatim", () => {
    const slice = selectDriverIntelligence(
      bundle([
        driver({
          driver_id: "VER",
          disagreement: {
            status: "AVAILABLE",
            p_model: 0.401,
            p_model_family: "INDEPENDENT_BINARY",
            p_simulation: 0.355,
            p_simulation_family: "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY",
            signed_gap: -0.046,
            absolute_gap: 0.046,
            model_rank: 1,
            simulation_rank: 1,
            model_inside_simulation_wilson: false,
          },
        }),
      ]),
      "VER",
    );
    assert.equal(slice.driver?.modelRank, 1);
    assert.equal(slice.bundle.leaderModel, "VER");
    assert.equal(
      slice.bundle.sensitivityReason,
      "no perturbation range registered",
    );
  });
});
