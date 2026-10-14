import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

// Wiring + request + scope guards for V3.10F driver telemetry. Source
// characterisation tests (repo precedent: intelligenceIntegration.test.ts):
// they pin one race-scoped request cached per race, local re-slice on
// driver switch, selector-only data flow into components, and no science.
// Run with `node --test telemetryIntegration.test.ts`.

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const SELECTOR = read("./telemetry.ts");
const HOOK = read("../hooks/useDriverTelemetry.ts");
const PANEL = read("../components/DriverTelemetry.tsx");
const VIEW = read("../components/PitWallView.tsx");
const DRIVER_PANEL = read("../components/DriverPanel.tsx");

const F_SOURCES = [SELECTOR, HOOK, PANEL];

describe("telemetry request model", () => {
  it("exactly one race-scoped request, cached per race", () => {
    assert.ok(HOOK.includes("getRaceTelemetry("), "single race request");
    assert.ok(HOOK.includes("corpusCache"), "per-race module cache");
    assert.ok(!HOOK.includes("postUncertaintyCompare"), "no science fetch");
    const calls = HOOK.match(/getRaceTelemetry\(/g) ?? [];
    assert.equal(calls.length, 1, "one call site");
  });

  it("driver switches re-slice locally with zero requests", () => {
    assert.ok(
      PANEL.includes("selectCompletedDriverLaps("),
      "panel slices locally",
    );
    assert.ok(!PANEL.includes("getRaceTelemetry"), "panel never fetches");
    assert.ok(!PANEL.includes("fetch("), "no raw fetch in component");
  });

  it("components receive selector output only, never corpus totals", () => {
    for (const src of [PANEL]) {
      assert.ok(!src.includes("lap_count"), "no total lap count in UI");
      assert.ok(!src.includes("stint_count"), "no total stint count in UI");
      assert.ok(!src.includes(".laps.length"), "no corpus length in UI");
      assert.ok(!src.includes("corpus.laps"), "no raw corpus laps in UI");
      assert.ok(!src.includes("corpus.stints"), "no raw corpus stints in UI");
    }
  });
});

describe("telemetry scope guards", () => {
  it("no science, strategy, counterfactual, or prediction reads", () => {
    const forbidden = [
      "MC2",
      "simulations/race",
      "strategies/compare",
      "counterfactuals/compare",
      "consensus/compare",
      "postUncertaintyCompare",
      "predict/ensemble",
      "degradation",
      "slope",
      "regression",
    ];
    for (const src of F_SOURCES) {
      for (const token of forbidden) {
        assert.ok(!src.includes(token), `F layer must not touch ${token}`);
      }
    }
  });

  it("no strategy recommendation or counterfactual language", () => {
    const advisory = [
      "PIT NOW",
      "STAY OUT",
      "PIT NEXT LAP",
      "what if",
      "should pit",
      "recommend",
    ];
    for (const src of F_SOURCES) {
      for (const token of advisory) {
        assert.ok(
          !src.toLowerCase().includes(token.toLowerCase()),
          `F layer must not advise ${token}`,
        );
      }
    }
  });

  it("no qualitative sector labels or causal explanations", () => {
    // "Pit lap" and "Synthetic source row" are factual source tags, not
    // performance judgments; the ban targets evaluative language.
    const qualitative = ["weak sector", "poor", "tyre degradation", "traffic loss", "driver mistake", "because of tyres"];
    for (const src of F_SOURCES) {
      for (const token of qualitative) {
        assert.ok(
          !src.toLowerCase().includes(token),
          `F layer must not judge ${token}`,
        );
      }
    }
    assert.ok(
      PANEL.includes("descriptive differences, not explanations"),
      "delta honesty oath rendered",
    );
  });

  it("telemetry defaults closed and stays out of L0", () => {
    assert.equal(
      (PANEL.match(/^\s*<details>$/gm) ?? []).length,
      2,
      "exactly two disclosures",
    );
    assert.ok(!PANEL.includes("open="), "no forced-open state");
    assert.ok(!PANEL.includes("defaultOpen"), "native closed default");
  });

  it("workspace identity untouched by telemetry", () => {
    for (const src of F_SOURCES) {
      assert.ok(!src.includes("setRaceId"), "no race authority");
      assert.ok(!src.includes("setFrameIndex"), "no frame authority");
    }
    assert.ok(VIEW.includes("anchor_state_time_s"), "clock from the frame");
    assert.ok(DRIVER_PANEL.includes("DriverTelemetry"), "panel hosts F");
  });
});
