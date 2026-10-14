import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

// Wiring + request + scope guards for V3.10E driver intelligence. Source
// characterisation tests (repo precedent): they pin that the compact
// intelligence consumes the frozen uncertainty bundle through one hook,
// slices locally per driver, refuses honestly, and pulls no other science.
// Run with `node --test intelligenceIntegration.test.ts`.

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const VIEW = read("../components/PitWallView.tsx");
const DRIVER = read("../components/DriverPanel.tsx");
const HOOK = read("../hooks/useDriverIntelligence.ts");
const SLICE = read("./driverIntelligence.ts");

const E_SOURCES = [VIEW, DRIVER, HOOK, SLICE];

describe("intelligence data flow", () => {
  it("one hook owns the bundle; the view anchors it to the frame", () => {
    assert.ok(
      HOOK.includes("getUncertaintyAvailability"),
      "cheap availability first",
    );
    assert.ok(HOOK.includes("postUncertaintyCompare"), "at most one compare");
    assert.ok(
      VIEW.includes("useDriverIntelligence("),
      "view owns the hook call",
    );
    assert.ok(
      VIEW.includes("anchor_lap_number"),
      "anchor comes from the frame",
    );
    assert.ok(
      VIEW.includes("anchor_state_time_s"),
      "anchor time comes from the frame",
    );
  });

  it("driver switching slices locally and issues no request", () => {
    assert.ok(
      DRIVER.includes("selectDriverIntelligence("),
      "panel slices the bundle",
    );
    assert.ok(!DRIVER.includes("postUncertaintyCompare"), "panel never fetches");
    assert.ok(!DRIVER.includes("getUncertaintyAvailability"), "panel never fetches");
    assert.ok(!DRIVER.includes("useState"), "no local intelligence state");
  });

  it("bundles are memoized per anchor with stale guards", () => {
    assert.ok(HOOK.includes("bundleCache"), "per-anchor memo");
    assert.ok(HOOK.includes("AbortController"), "abortable");
    assert.ok(HOOK.includes("mountedRef"), "stale guard");
  });
});

describe("compact presentation", () => {
  it("L0 shows MODEL / SIM / DIFFERENCE plus a precision line", () => {
    assert.ok(DRIVER.includes('label="Model"'), "model value");
    assert.ok(DRIVER.includes('label="Simulation"'), "simulation value");
    assert.ok(DRIVER.includes('label="Difference"'), "signed gap value");
    assert.ok(DRIVER.includes("validFuturesN"), "precision line needs n");
    assert.ok(DRIVER.includes("wilsonLower"), "precision line needs interval");
  });

  it("DETAILS carries ranks, leaders, Wilson, U3, families, expert links", () => {
    assert.ok(DRIVER.includes("Model rank"), "model rank");
    assert.ok(DRIVER.includes("Simulation rank"), "simulation rank");
    assert.ok(DRIVER.includes("WilsonViz"), "reused interval viz");
    assert.ok(DRIVER.includes("Simulator sensitivity"), "U3 limitation");
    assert.ok(DRIVER.includes("modelFamily"), "model family");
    assert.ok(DRIVER.includes("simulationFamily"), "simulation family");
    assert.ok(DRIVER.includes("<details"), "native disclosure kept");
    assert.ok(DRIVER.includes("Expert: consensus"), "consensus deep link");
    assert.ok(DRIVER.includes("Expert: uncertainty"), "uncertainty deep link");
  });

  it("frame facts render exactly once (no duplicated grids)", () => {
    // Regression guard: the facts block must appear a single time; the
    // only other <dl> elements are the L0 MODEL/SIM/Δ row and the DETAILS
    // rank pair.
    assert.equal(
      (DRIVER.match(/label="Gap leader"/g) ?? []).length,
      1,
      "one facts grid",
    );
    assert.equal(
      (DRIVER.match(/<dl/g) ?? []).length,
      3,
      "facts + L0 row + DETAILS ranks",
    );
  });

  it("expert links carry canonical identity through the B helper", () => {
    assert.ok(VIEW.includes("workspaceDeepLink("), "B deep-link helper");
    assert.ok(VIEW.includes('"/consensus"'), "consensus target");
    assert.ok(VIEW.includes('"/uncertainty"'), "uncertainty target");
  });

  it("refusals render as status with recovery, never zeros", () => {
    assert.ok(DRIVER.includes("not-comparable"), "availability refusal");
    assert.ok(DRIVER.includes("unsupported"), "typed refusal");
    assert.ok(DRIVER.includes("refusalCopy("), "frozen refusal language");
    assert.ok(DRIVER.includes("Missing is"), "missing-is-not-zero");
    assert.ok(DRIVER.includes("Retry intelligence"), "recovery");
    assert.ok(DRIVER.includes("nothing is substituted"), "no substitution");
  });
});

describe("intelligence request audit", () => {
  it("touches exactly the frozen uncertainty product API", () => {
    // monte_carlo_sampling is a verbatim frozen field read (data, not
    // execution); the ban targets engines and sibling product endpoints.
    const forbidden = [
      "consensus/compare",
      "strategies/compare",
      "counterfactuals/compare",
      "simulations/race",
      "predict/ensemble",
      "predict/single",
      "MC2",
    ];
    for (const src of E_SOURCES) {
      for (const token of forbidden) {
        assert.ok(!src.includes(token), `E layer must not touch ${token}`);
      }
      const imports = src
        .split("\n")
        .filter((line) => /^\s*import[ (]/.test(line))
        .join("\n");
      assert.ok(!imports.includes("simulator"), "no simulator imports");
      assert.ok(!imports.includes("strategy"), "no strategy imports");
    }
  });

  it("no blending, verdicts, recommendations, or scores", () => {
    // "No recommendation is shown here" (strategy placeholder denial) is
    // honest product language; the ban targets advisory claims.
    // "never blended" (side-by-side honesty oath) is required language;
    // the ban targets actual blending claims, of which there are none
    // (single-source bundle, verbatim render, no fusion arithmetic).
    const advisory = [
      "should pit",
      "should stay",
      "best strategy",
      "we recommend",
      "recommended strategy",
      "optimal",
      "confidence",
      "winner",
    ];
    for (const src of E_SOURCES) {
      for (const token of advisory) {
        assert.ok(
          !src.toLowerCase().includes(token),
          `E layer must not claim ${token}`,
        );
      }
    }
    assert.ok(DRIVER.includes("never"), "disagreement-not-verdict language");
  });
});

describe("E scope guards", () => {
  it("no sector/lap, stint-history, or strategy/counterfactual work", () => {
    for (const src of E_SOURCES) {
      assert.ok(!src.includes("sector"), "sectors belong to F");
      assert.ok(!src.includes("stint_history"), "stints belong to F");
      assert.ok(!src.includes("counterfactual"), "counterfactuals belong to G");
    }
    // V3.10G owns the strategy entry: the view renders the contextual
    // DecisionExploration (explicit-run only); E still holds no strategy.
    assert.ok(VIEW.includes("DecisionExploration"), "G entry composed");
    assert.ok(!HOOK.includes("strateg"), "E hook holds no strategy");
    assert.ok(!SLICE.includes("strateg"), "E slice holds no strategy");
  });

  it("workspace and event contracts flow through unchanged", () => {
    assert.ok(VIEW.includes("visibleEvents("), "causal gating kept");
    assert.ok(VIEW.includes("usePitWallRace("), "C data hook kept");
    assert.ok(VIEW.includes("usePitWallEvents("), "D event hook kept");
    for (const src of E_SOURCES) {
      assert.ok(!src.includes("setRaceId"), "no race authority");
      assert.ok(!src.includes("setFrameIndex"), "no frame authority");
    }
  });
});
