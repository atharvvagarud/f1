import { strict as assert } from "node:assert";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

// Structural integrity guards for the Pit Wall shell (V3.10C). Source
// characterisation tests (repo precedent: replayIntegration.test.ts,
// workspaceIntegrity.test.ts): they pin workspace consumption, reuse,
// navigation, and no-fake-data without executing React. Run with
// `node --test pitWallIntegrity.test.ts` (Node >= 22, no new dependencies).

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const VIEW = read("../components/PitWallView.tsx");
const HOOK = read("../hooks/usePitWall.ts");
const DRIVER = read("../components/DriverPanel.tsx");
const DECISION = read("../components/DecisionExploration.tsx");
const DECISION_HOOK = read("../hooks/useDecisionExploration.ts");
const DECISION_ADAPTER = read("./decisionAdapter.ts");
const DECISION_DISPLAY = read("./decisionDisplay.ts");
const TRANSPORT = read("../components/PitWallTransport.tsx");
const FACTS = read("./driverFacts.ts");
const PAGE = read("../../../app/pit-wall/page.tsx");
const COMMAND_BAR = read("../../../components/shell/CommandBar.tsx");

const PITWALL_SOURCES = [VIEW, HOOK, DRIVER, TRANSPORT, FACTS, PAGE];
// V3.10G contextual surfaces: availability-gated, explicit-run only.
const G_SOURCES = [DECISION, DECISION_HOOK, DECISION_ADAPTER, DECISION_DISPLAY];

describe("pit-wall route", () => {
  it("/pit-wall route exists and renders the shell with metadata", () => {
    assert.ok(PAGE.includes("PitWallView"), "page renders PitWallView");
    assert.ok(PAGE.includes("Pit Wall"), "page carries Pit Wall metadata");
    assert.ok(VIEW.includes("<h1"), "shell has exactly one h1");
    assert.equal(
      VIEW.match(/<h1/g)?.length ?? 0,
      1,
      "exactly one h1 in the shell",
    );
  });

  it("all pre-existing routes still exist (no deletion)", () => {
    const routes = [
      "replay",
      "simulator",
      "strategy",
      "counterfactuals",
      "consensus",
      "uncertainty",
      "models",
      "about",
    ];
    for (const route of routes) {
      assert.ok(
        COMMAND_BAR.includes(`"/${route}"`),
        `/${route} stays reachable`,
      );
    }
    // /spatial is unlinked by design (dev harness) but must still exist.
    assert.ok(
      existsSync(join(here, "../../../app/spatial/page.tsx")),
      "/spatial route still exists",
    );
  });
});

describe("workspace-state consumption", () => {
  it("pit-wall identity comes from the workspace provider, not local state", () => {
    assert.ok(HOOK.includes("useWorkspace()"), "hook consumes workspace");
    assert.ok(
      VIEW.includes("usePitWallRaces") && VIEW.includes("usePitWallRace"),
      "view consumes pit-wall hooks",
    );
    assert.ok(VIEW.includes("useWorkspace()"), "shell reads workspace identity");
    for (const [name, setter] of [
      ["raceId", "setRaceId"],
      ["frameIndex", "setFrameIndex"],
      ["selectedDriver", "setSelectedDriver"],
      ["selection", "setSelection"],
    ] as const) {
      void name;
      assert.ok(
        !HOOK.includes(`${setter}(`) && !HOOK.includes(`${setter}<`),
        `hook must not own ${setter}`,
      );
    }
  });

  it("race, frame, and driver flow from workspace state", () => {
    assert.ok(HOOK.includes("workspace.state"), "reads canonical state");
    assert.ok(HOOK.includes("workspace.setRace"), "race via SET_RACE");
    assert.ok(HOOK.includes("workspace.seekFrame"), "moves via SEEK_FRAME");
    assert.ok(
      HOOK.includes("workspace.selectDriver"),
      "selection via workspace",
    );
    assert.ok(HOOK.includes("workspace.clearDriver"), "clearing via workspace");
  });

  it("driver panel holds no selection copy", () => {
    assert.ok(!DRIVER.includes("useState"), "no local state in driver panel");
    assert.ok(DRIVER.includes("selectedDriverId"), "driven by prop");
    assert.ok(DRIVER.includes("onSelect"), "selection delegates outward");
  });

  it("transport holds no clock", () => {
    assert.ok(!TRANSPORT.includes("useState"), "no local state in transport");
    assert.ok(!TRANSPORT.includes("useEffect"), "no loops in transport");
  });
});

describe("replay reuse", () => {
  it("composes validated replay components instead of forking ReplayView", () => {
    for (const component of [
      "RaceSelector",
      "ContextBar",
      "SpatialTrackPanel",
      "StandingsTable",
      "TimelineScrubber",
    ]) {
      assert.ok(VIEW.includes(component), `reuses ${component}`);
    }
    assert.ok(!VIEW.includes("ReplayView"), "does not embed ReplayView");
  });

  it("fetches only through existing replay data boundaries", () => {
    assert.ok(HOOK.includes("getV2Races"), "served races boundary");
    assert.ok(HOOK.includes("fetchFullTimeline"), "timeline boundary");
    assert.ok(HOOK.includes("getReplayFrame"), "frame boundary");
    assert.ok(HOOK.includes("intervalForSpeed"), "playback timing boundary");
  });

  it("issues no science requests except explicit G exploration", () => {
    // Default shell + replay path stay science-free. V3.10G adds exactly
    // two frozen compare endpoints, reachable only through the G hook's
    // explicit run paths (characterised below) — never on state change.
    const forbiddenEverywhere = [
      "consensus/compare",
      "uncertainty/compare",
      "simulations/race",
      "predict/ensemble",
      "predict/single",
      "MC2",
    ];
    for (const src of [...PITWALL_SOURCES, ...G_SOURCES]) {
      for (const token of forbiddenEverywhere) {
        assert.ok(!src.includes(token), `pit-wall must not touch ${token}`);
      }
    }
    for (const src of PITWALL_SOURCES) {
      assert.ok(!src.includes("strategies/compare"), "G-only endpoint");
      assert.ok(
        !src.includes("counterfactuals/compare"),
        "G-only endpoint",
      );
    }
  });

  it("G compare requests are explicit, cached, and abort-safe", () => {
    assert.ok(
      DECISION_HOOK.includes('mode: "cached"'),
      "strategy compare is cache-first",
    );
    assert.ok(
      !DECISION_HOOK.includes('mode: "live"'),
      "live execution unreachable from pit wall",
    );
    assert.ok(
      DECISION_HOOK.includes("REFERENCE_VS_PLAN"),
      "counterfactual compare is reference-vs-plan only",
    );
    assert.ok(DECISION_HOOK.includes("AbortController"), "abortable");
    assert.ok(
      DECISION_HOOK.includes("requestIdRef"),
      "stale-response guards",
    );
    // Availability derives entry state; comparison runs only from the
    // explicit buttons (no effect-driven run, no auto-run on scrub).
    assert.ok(
      DECISION.includes("onClick={onRun}") || DECISION.includes("onRun={"),
      "strategy run is button-triggered",
    );
    assert.ok(DECISION.includes('type="submit"'), "alternative run is form-triggered");
  });
});

describe("no fake intelligence", () => {
  it("shows no numeric probabilities, deltas, or gaps-as-text", () => {
    for (const src of [VIEW, DRIVER, TRANSPORT, PAGE]) {
      assert.ok(!/\d+\.\d+%/.test(src), "no decimal percentages");
      assert.ok(!/MODEL\s+\d/.test(src), "no MODEL numbers");
      assert.ok(!/SIM\s+\d/.test(src), "no SIM numbers");
    }
  });

  it("uses no recommendation, winner, or confidence language", () => {
    // G surfaces are scanned exhaustively (including the forbidden-phrase
    // guard list itself, which lives in decisionDisplay.ts) by
    // decisionDisplay.test.ts; here the hook + component prose stays clean.
    for (const src of [...PITWALL_SOURCES, DECISION, DECISION_HOOK]) {
      const lower = src.toLowerCase();
      assert.ok(!lower.includes("optimal"), "no optimal-strategy language");
      assert.ok(!lower.includes("best strategy"), "no best-strategy language");
      assert.ok(!lower.includes("confidence"), "no confidence scores");
      assert.ok(!lower.includes("source winner"), "no source winner");
      assert.ok(!src.includes("INDEPENDENT_BINARY"), "no expert jargon");
      assert.ok(!src.includes("MUTUALLY_EXCLUSIVE"), "no expert jargon");
      assert.ok(!src.includes("PROVENANCE_UNAVAILABLE"), "no expert jargon");
    }
  });

  it("strategy entry is contextual and explicit, not faked", () => {
    // V3.10G owns this entry: availability-gated Explore actions through
    // the frozen clients, explicit-run only, with honest unsupported states.
    // No disabled placeholder, no fabricated numbers, no advice.
    assert.ok(VIEW.includes("DecisionExploration"), "G entry composed");
    assert.ok(DECISION.includes("Explore strategy"), "strategy entry exists");
    assert.ok(DECISION.includes("Explore alternative"), "alternative entry exists");
    assert.ok(
      DECISION.includes("Strategy unavailable at this state"),
      "unsupported stays unsupported",
    );
    assert.ok(
      DECISION.includes("Alternative unavailable at this state"),
      "unsupported stays unsupported",
    );
    assert.ok(
      DECISION.includes("compared with the simulated no-intervention reference"),
      "reference framing visible",
    );
    assert.ok(
      DECISION.includes("Simulator-conditional comparison"),
      "counterfactual qualification visible",
    );
  });
});

describe("simplified navigation", () => {
  it("primary nav is PIT WALL / RACES / MODELS / ABOUT", () => {
    assert.ok(COMMAND_BAR.includes('"/pit-wall"'), "PIT WALL mapped");
    assert.ok(COMMAND_BAR.includes("Pit wall"), "PIT WALL labeled");
    assert.ok(COMMAND_BAR.includes('Races'), "RACES labeled");
    assert.ok(COMMAND_BAR.includes('"/models"'), "MODELS mapped");
    assert.ok(COMMAND_BAR.includes('"/about"'), "ABOUT mapped");
  });

  it("RACES maps to the existing race-selection surface", () => {
    const primaryBlock = COMMAND_BAR.slice(
      0,
      COMMAND_BAR.indexOf("EXPERT_ITEMS"),
    );
    assert.ok(primaryBlock.includes('"/replay"'), "RACES -> /replay");
  });

  it("expert routes stay reachable in a subordinate strip", () => {
    assert.ok(COMMAND_BAR.includes('aria-label="Expert"'), "expert strip");
    for (const href of [
      "/",
      "/replay",
      "/simulator",
      "/consensus",
      "/uncertainty",
      "/strategy",
      "/counterfactuals",
    ]) {
      assert.ok(
        COMMAND_BAR.slice(COMMAND_BAR.indexOf("EXPERT_ITEMS")).includes(
          `"${href}"`,
        ),
        `expert strip keeps ${href}`,
      );
    }
  });

  it("navigation keeps current-page state for both strips", () => {
    assert.equal(
      COMMAND_BAR.match(/aria-current/g)?.length ?? 0,
      2,
      "aria-current in primary and expert nav",
    );
  });
});

describe("progressive disclosure foundation", () => {
  it("uses one native details primitive, not competing modals", () => {
    assert.ok(DRIVER.includes("<details"), "DETAILS primitive exists");
    assert.ok(DRIVER.includes("<summary"), "disclosure has a summary");
    assert.ok(!VIEW.includes("modal"), "no modal pattern");
    assert.ok(!VIEW.includes("Dialog"), "no dialog pattern");
  });
});

describe("accessibility structure", () => {
  it("regions carry landmarks and headings", () => {
    for (const label of [
      "Race state",
      "Track replay",
      "Selected driver",
      "Running order",
      "Race control",
      "Strategy",
      "Alternative",
      "Replay timeline",
    ]) {
      assert.ok(
        VIEW.includes(label) || DRIVER.includes(label) || DECISION.includes(label),
        label,
      );
    }
    assert.ok(VIEW.includes('role="status"'), "polite status region");
    assert.ok(VIEW.includes('role="alert"'), "error alerts");
    assert.ok(
      TRANSPORT.includes('aria-label="Pit wall transport controls"'),
      "transport group labeled",
    );
  });

  it("interactive controls are native and keyboard-operable", () => {
    assert.ok(DRIVER.includes("<select"), "native driver picker");
    assert.ok(DRIVER.includes("<label"), "picker is labeled");
    assert.ok(TRANSPORT.includes("<button"), "native transport buttons");
    assert.ok(TRANSPORT.includes('aria-label="Play replay"'), "play labeled");
    assert.ok(TRANSPORT.includes('aria-label="Pause replay"'), "pause labeled");
    for (const src of [DRIVER, TRANSPORT]) {
      assert.ok(src.includes("focus-visible:"), "visible focus styles");
    }
  });
});
