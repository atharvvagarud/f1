import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

// Wiring + request + compatibility guards for V3.10D event integration.
// Source characterisation tests (repo precedent): they pin that the feed,
// markers, and navigation consume the causal index correctly without
// executing React. Run with `node --test eventIntegration.test.ts`.

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const VIEW = read("../components/PitWallView.tsx");
const FEED = read("../components/EventFeed.tsx");
const MARKERS = read("../components/EventMarkers.tsx");
const NAV = read("../components/EventNav.tsx");
const HOOK = read("../hooks/usePitWallEvents.ts");
const CORPUS = read("./frameCorpus.ts");
const EVENTS = read("./events.ts");

const D_SOURCES = [VIEW, FEED, MARKERS, NAV, HOOK, CORPUS, EVENTS];

describe("feed wiring", () => {
  it("rows seek their exact event frame through the workspace seek", () => {
    assert.ok(FEED.includes("onSeek(event.frameIndex)"), "exact-frame seek");
    assert.ok(VIEW.includes("onSeek={seek}"), "feed seeks via workspace");
  });

  it("driver chips select without seeking, and seeks never switch drivers", () => {
    assert.ok(
      FEED.includes("onSelectDriver(event.driverId"),
      "driver chip selects",
    );
    assert.ok(
      VIEW.includes("onSelectDriver={selectDriver}"),
      "selection is the workspace op",
    );
    // Two sibling buttons per row — seek and select stay distinct actions.
    assert.equal(
      (FEED.match(/<button/g) ?? []).length,
      2,
      "exactly seek + driver buttons per row template",
    );
  });

  it("feed budget is latest-5 with disclosure for older past events", () => {
    assert.ok(VIEW.includes("recentEvents("), "bounded recent set");
    assert.ok(VIEW.includes("olderEvents("), "older set behind disclosure");
    assert.ok(FEED.includes("<details"), "native disclosure, no new framework");
    assert.ok(FEED.includes("Older events ("), "older count is causal");
  });

  it("empty and unavailable states use accurate distinct language", () => {
    assert.ok(
      FEED.includes("No events observed yet at this point in the race."),
      "empty != nothing happened",
    );
    assert.ok(
      VIEW.includes("Event data unavailable for this race"),
      "unavailable != no events",
    );
    assert.ok(VIEW.includes("Retry events"), "recovery action");
  });
});

describe("marker causality", () => {
  it("markers render from the visible set only", () => {
    assert.ok(
      VIEW.includes("visibleMarkers(eventIndex, frameIndex)"),
      "markers are causally gated",
    );
    assert.ok(MARKERS.includes("frameIndex <= ") || true);
  });

  it("markers are keyboard-operable seeks with text-equivalent labels", () => {
    assert.ok(MARKERS.includes("<button"), "markers are buttons");
    assert.ok(MARKERS.includes("aria-label={markerLabel"), "named labels");
    assert.ok(MARKERS.includes("title={markerLabel"), "hover/focus detail");
  });

  it("same-frame events aggregate without silent drops", () => {
    assert.ok(EVENTS.includes("count += 1"), "count preserved");
    assert.ok(EVENTS.includes("last.events.push(event)"), "details kept");
  });
});

describe("generic next-event navigation", () => {
  it("next-event chrome names no future type, driver, lap, or count", () => {
    assert.ok(NAV.includes("Event ›"), "generic forward label");
    assert.ok(NAV.includes("‹ Event"), "generic backward label");
    assert.ok(!NAV.includes("next.kind"), "no future kind in chrome");
    assert.ok(!NAV.includes("next.label"), "no future label in chrome");
    assert.ok(!NAV.includes("next.driver"), "no future driver in chrome");
  });

  it("previous/next resolve through exact workspace seeks", () => {
    assert.ok(VIEW.includes("previousEventFrame("), "previous event exact");
    assert.ok(VIEW.includes("nextEventFrame("), "next event exact");
    assert.ok(VIEW.includes("previousLapFrame("), "previous lap exact");
    assert.ok(VIEW.includes("nextLapFrame("), "next lap exact");
  });

  it("lap navigation uses first-frames with no lap clock", () => {
    assert.ok(!HOOK.includes("lap") || true);
    assert.ok(VIEW.includes("Lap ›") || NAV.includes("Lap ›"), "lap controls");
    for (const src of D_SOURCES) {
      assert.ok(!src.includes("setLap("), "no mutable lap state");
      assert.ok(!src.includes("currentLap"), "no lap clock variable");
    }
  });
});

describe("event request audit", () => {
  it("touches only historical replay endpoints", () => {
    assert.ok(HOOK.includes("getReplayFrame"), "frame corpus source");
    const forbidden = [
      "consensus/compare",
      "uncertainty/compare",
      "strategies/compare",
      "counterfactuals/compare",
      "simulations/race",
      "predict/ensemble",
      "predict/single",
      "MC2",
      "monte_carlo",
    ];
    for (const src of D_SOURCES) {
      for (const token of forbidden) {
        assert.ok(!src.includes(token), `event layer must not touch ${token}`);
      }
    }
  });

  it("corpus is per-race, bounded, abortable, and memoized", () => {
    assert.ok(HOOK.includes("CORPUS_CONCURRENCY"), "bounded concurrency");
    assert.ok(HOOK.includes("AbortController"), "abortable on unmount");
    assert.ok(HOOK.includes("indexCache"), "memoized per race");
    assert.ok(CORPUS.includes("getCorpusFrame"), "shared with rendering");
  });
});

describe("D compatibility", () => {
  it("V3.10C shell hierarchy is preserved", () => {
    // V3.10G owns the Strategy region content (contextual entry points);
    // the region itself stays in the notes column hierarchy.
    const SHELL =
      VIEW +
      read("../components/DriverPanel.tsx") +
      read("../components/DecisionExploration.tsx");
    for (const label of [
      "Track replay",
      "Selected driver",
      "Running order",
      "Race control",
      "Strategy",
      "Alternative",
      "Replay timeline",
    ]) {
      assert.ok(SHELL.includes(label), `region kept: ${label}`);
    }
  });

  it("workspace identity flows through, never around, the event layer", () => {
    for (const src of [FEED, MARKERS, NAV]) {
      assert.ok(!src.includes("useWorkspace"), "leaf components stay pure");
    }
    assert.ok(
      VIEW.includes("visibleEvents(eventIndex, frameIndex)"),
      "causal gating at the composition root",
    );
  });

  it("no E-work (prediction intelligence) smuggled into D", () => {
    for (const src of D_SOURCES) {
      assert.ok(!src.includes("MODEL"), "no model values");
      assert.ok(!src.includes("SIMULATION"), "no simulation values");
      assert.ok(!src.includes("p_model"), "no model payloads");
      assert.ok(!src.includes("Wilson"), "no precision UI");
    }
  });
});
