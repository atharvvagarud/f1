// Pit-wall product-polish guards (V3.10H).
//
// Whole-product consolidation pins without executing React (repo
// precedent): hierarchy order, disclosure vocabulary, live-region
// singularity, same-value hydration regression, explicit-run request
// budget, route preservation, and extended copy bounds. Run with
// `node --test productPolish.test.ts`.

import { strict as assert } from "node:assert";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const VIEW = read("../components/PitWallView.tsx");
const DRIVER = read("../components/DriverPanel.tsx");
const TELEMETRY = read("../components/DriverTelemetry.tsx");
const DECISION = read("../components/DecisionExploration.tsx");
const DECISION_HOOK = read("../hooks/useDecisionExploration.ts");
const HYDRATION = read("../../workspace/hooks/useExpertHydration.ts");
const SPATIAL = read("../../replay/components/SpatialTrackPanel.tsx");
const STRATEGY_VIEW = read("../../strategy/components/Strategy2View.tsx");
const CF_VIEW = read("../../counterfactuals/components/CounterfactualView.tsx");
const COMMAND_BAR = read("../../../components/shell/CommandBar.tsx");
const INTELLIGENCE_HOOK = read("../hooks/useDriverIntelligence.ts");
const TELEMETRY_HOOK = read("../hooks/useDriverTelemetry.ts");

describe("information hierarchy", () => {
  it("regions compose in race-first order", () => {
    for (const [first, second] of [
      ["Race state", "Track replay"],
      ["Track replay", "Running order"],
      ["Running order", "Replay timeline"],
    ] as const) {
      assert.ok(
        VIEW.indexOf(first) < VIEW.indexOf(second),
        `${first} precedes ${second}`,
      );
    }
    assert.ok(VIEW.includes("DriverPanel"), "driver region composed");
    assert.ok(VIEW.includes("DecisionExploration"), "decisions composed");
  });

  it("track grid area precedes the driver column", () => {
    const areas = VIEW.indexOf("grid-template-areas");
    assert.ok(areas >= 0, "explicit grid areas");
    const template = VIEW.slice(areas, areas + 400);
    assert.ok(
      template.indexOf("track") < template.indexOf("driver"),
      "track area before driver area",
    );
  });

  it("decisions stay subordinate: no permanent matrix or builder", () => {
    assert.ok(DECISION.includes("Explore strategy"), "strategy gated by intent");
    assert.ok(DECISION.includes("Explore alternative"), "alternative gated by intent");
    assert.ok(!DECISION.includes("open="), "results never forced open");
    assert.ok(!DECISION.includes("defaultOpen"), "native closed defaults");
  });

  it("decision headings are flat h2 pairs with no jumps", () => {
    assert.equal((DECISION.match(/<h2/g) ?? []).length, 2, "Strategy + Alternative");
    assert.ok(!DECISION.includes("<h1"), "no h1 in decisions");
    assert.ok(!DECISION.includes("<h3"), "no heading jump in decisions");
  });

  it("primary nav remains four concepts", () => {
    for (const href of ["/pit-wall", "/replay", "/models", "/about"]) {
      assert.ok(COMMAND_BAR.includes(`"${href}"`), `primary keeps ${href}`);
    }
  });
});

describe("disclosure consolidation", () => {
  const ALLOWED = new Set([
    "Details",
    "Lap / sectors",
    "Tyre history",
    "How to read",
    "Explore alternative",
  ]);

  it("disclosure vocabulary stays small and consistent", () => {
    for (const [name, src] of [
      ["DriverPanel", DRIVER],
      ["DriverTelemetry", TELEMETRY],
      ["DecisionExploration", DECISION],
    ] as const) {
      const summaries = [...src.matchAll(/<summary[^>]*>([\s\S]*?)<\/summary>/g)];
      assert.ok(summaries.length > 0, `${name} uses native disclosure`);
      for (const match of summaries) {
        const label = match[1].replace(/\{[^}]*\}/g, "").trim();
        const ok =
          ALLOWED.has(label) ||
          label.startsWith("Older events (") ||
          label === "";
        assert.ok(ok, `${name} disclosure label in vocabulary: ${label.slice(0, 40)}`);
      }
    }
  });

  it("no competing disclosure framework", () => {
    for (const [name, src] of [
      ["PitWallView", VIEW],
      ["DriverPanel", DRIVER],
      ["DriverTelemetry", TELEMETRY],
      ["DecisionExploration", DECISION],
    ] as const) {
      assert.ok(!src.includes("<dialog"), `${name}: no dialog`);
      assert.ok(!src.includes("Dialog"), `${name}: no Dialog`);
      assert.ok(!src.toLowerCase().includes("drawer"), `${name}: no drawer`);
      assert.ok(!src.includes("modal"), `${name}: no modal`);
    }
  });
});

describe("live-region singularity (no announcement spam)", () => {
  it("pit-wall transport status has one announcer", () => {
    // The visible timeline line mirrors the sr-only status text without
    // its own live region; while playing the message is constant.
    assert.ok(VIEW.includes('role="status"'), "single polite announcer");
    assert.ok(
      VIEW.includes("Single playback announcer"),
      "gating rationale pinned",
    );
    assert.ok(
      !VIEW.includes('{frameLoading && "Loading frame…"}`') &&
        !VIEW.includes('{frameLoading && "Loading frame…"}\n'),
      "no per-frame loading flicker in the status line",
    );
  });

  it("spatial pending cue is calm while playing, unchanged elsewhere", () => {
    assert.ok(SPATIAL.includes("announcePending = true"), "replay default kept");
    assert.ok(
      VIEW.includes("announcePending={playbackStatus"),
      "pit wall calms announcements while playing",
    );
  });
});

describe("same-value hydration regression (V3.10G bug stays fixed)", () => {
  it("identical values never re-trigger selection", () => {
    assert.ok(
      HYDRATION.includes("args.frameIndex !== deepLink.frameIndex"),
      "same frame skipped",
    );
    assert.ok(HYDRATION.includes("args.driverKey"), "driver identity compared");
    assert.ok(HYDRATION.includes("appliedRef"), "hydration applies at most once");
    assert.ok(
      HYDRATION.includes("deepLink.frameIndex < args.totalFrames"),
      "exact frame only, never clamped",
    );
  });

  it("both expert surfaces supply current identity for the skip", () => {
    for (const [name, src] of [
      ["Strategy2View", STRATEGY_VIEW],
      ["CounterfactualView", CF_VIEW],
    ] as const) {
      assert.ok(src.includes("frameIndex,"), `${name} passes frameIndex`);
      assert.ok(src.includes("driverKey:"), `${name} passes driverKey`);
    }
  });
});

describe("explicit-run request budget (source guards)", () => {
  it("compare endpoints have exactly one call site each, inside run paths", () => {
    assert.equal(
      (DECISION_HOOK.match(/postStrategyV3Compare\(/g) ?? []).length,
      1,
      "single strategy compare call site",
    );
    assert.equal(
      (DECISION_HOOK.match(/postCounterfactualCompare\(/g) ?? []).length,
      1,
      "single counterfactual compare call site",
    );
    const [strategyHalf, cfHalf] = DECISION_HOOK.split("--- counterfactual ---");
    assert.ok(
      strategyHalf.indexOf("postStrategyV3Compare(") >
        strategyHalf.indexOf("const run"),
      "strategy compare only reachable from run",
    );
    assert.ok(
      cfHalf.indexOf("postCounterfactualCompare(") > cfHalf.indexOf("const run"),
      "counterfactual compare only reachable from run",
    );
  });

  it("effects fetch availability only, never comparisons", () => {
    assert.equal(
      (DECISION_HOOK.match(/getStrategyV3Availability\(/g) ?? []).length,
      1,
      "single catalogue fetch site",
    );
    assert.equal(
      (DECISION_HOOK.match(/getCounterfactualAvailability\(/g) ?? []).length,
      1,
      "single availability fetch site",
    );
  });

  it("stale verdicts cannot attach to a new identity", () => {
    assert.equal(
      (DECISION_HOOK.match(/fetched\.key === anchorJson/g) ?? []).length,
      2,
      "both hooks key verdicts by workspace identity",
    );
    assert.ok(
      (DECISION_HOOK.match(/abortRef\.current\?\.abort\(\)/g) ?? []).length >= 4,
      "abort coverage across retry/run/move",
    );
  });
});

describe("state-transition identity (source guards)", () => {
  it("intelligence bundles key on the full anchor", () => {
    assert.ok(
      INTELLIGENCE_HOOK.includes("anchor.anchorStateTimeS"),
      "anchor time in bundle key",
    );
  });

  it("telemetry corpus is race-scoped with identity check", () => {
    assert.ok(TELEMETRY_HOOK.includes("corpusCache"), "per-race memo");
    assert.ok(
      TELEMETRY_HOOK.includes("body.race_id !== raceId"),
      "race identity verified",
    );
  });

  it("race change remounts per-race followers", () => {
    assert.ok(VIEW.includes("key={raceId}"), "race remount boundary");
  });
});

describe("route preservation", () => {
  it("all eleven routes still exist", () => {
    for (const route of [
      "", "pit-wall", "replay", "simulator", "strategy", "counterfactuals",
      "consensus", "uncertainty", "models", "about", "spatial",
    ]) {
      const page = route === "" ? "page.tsx" : `${route}/page.tsx`;
      assert.ok(
        existsSync(join(here, "..", "..", "..", "app", page)),
        `route /${route} exists`,
      );
    }
  });

  it("expert strip keeps every destination directly reachable", () => {
    for (const href of [
      "/", "/replay", "/simulator", "/consensus", "/uncertainty",
      "/strategy", "/counterfactuals",
    ]) {
      assert.ok(COMMAND_BAR.includes(`"${href}"`), `expert keeps ${href}`);
    }
  });
});

describe("extended copy bounds (H language audit)", () => {
  // Single-word advice terms are pinned by earlier stage scans; H adds
  // identifier-safe phrases. Negation/comment/guard lines are excluded —
  // methodology copy may negate terms, never claim them.
  const TOKENS = [
    "should pit",
    "would have",
    "true probability",
    "predicted future",
    "causal effect",
    "real-world confidence",
    "reliable",
    "trustworthy",
    "source winner",
    "recommended",
  ];

  it("no unsupported claims across pit-wall surfaces", () => {
    for (const [name, src] of [
      ["PitWallView", VIEW],
      ["DriverPanel", DRIVER],
      ["DriverTelemetry", TELEMETRY],
      ["DecisionExploration", DECISION],
      ["DecisionHook", DECISION_HOOK],
    ] as const) {
      for (const line of src.split("\n")) {
        if (/FORBIDDEN_COPY|DECISION_FORBIDDEN|assert\.|^\s*\/\//.test(line)) continue;
        if (/never|not |no |n't|without|instead|missing is not/i.test(line)) continue;
        for (const token of TOKENS) {
          assert.doesNotMatch(
            line,
            new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
            `${name}: ${token}`,
          );
        }
      }
    }
  });
});
