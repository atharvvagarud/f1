// Cross-feature causal poison suite (V3.10H §38).
//
// At workspace T, future-contaminated fixtures are injected through every
// pit-wall boundary: events, laps/sectors, compounds/stints, intelligence
// anchors, and cross-state strategy/counterfactual identities. None may
// appear at T. Advancing to the legitimate boundary reveals them.
//
// Pure selectors + exact adapters only (no React, no fetch): the same
// boundaries the live surface reads. Run with `node --test
// causalIntegration.test.ts`.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { buildEventIndex, olderEvents, recentEvents, visibleEvents, visibleMarkers, type FrameDigest } from "./events.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { selectCompletedDriverLaps, selectReferenceLap, selectStintHistory, type TelemetryCorpus, type TelemetryLap } from "./telemetry.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { adaptDecisionTarget, eligibleNDomain, matchStrategyEntry } from "./decisionAdapter.ts";

function digest(frameIndex: number, over: Partial<FrameDigest> = {}): FrameDigest {
  return {
    frameIndex,
    anchorStateTimeS: 1000 + frameIndex * 90,
    leaderLap: 10,
    trackState: "all_clear",
    messageCategory: null,
    messageFlag: null,
    pits: {},
    ...over,
  };
}

function lap(over: Partial<TelemetryLap> & { lapNumber: number; observedAtS: number }): TelemetryLap {
  return {
    driverId: "HAM",
    lapTimeS: 95.0,
    sector1S: 30.0,
    sector2S: 35.0,
    sector3S: 30.0,
    compound: "MEDIUM",
    stintNumber: 1,
    pitEntry: null,
    pitExit: null,
    generated: false,
    ...over,
  };
}

describe("future events never appear at T", () => {
  // Frames 0..4 all-clear, frame 5 yellow (future flag), frame 6 all-clear.
  // Constant leader lap: no lap events, so T=4 is a clean empty past.
  const index = buildEventIndex("R", 7, [
    digest(0),
    digest(1),
    digest(2),
    digest(3),
    digest(4),
    digest(5, { trackState: "yellow" }),
    digest(6),
  ]);

  it("visible/recent/older sets exclude future frames", () => {
    for (const event of [...visibleEvents(index, 4), ...recentEvents(index, 4), ...olderEvents(index, 4)]) {
      assert.ok(event.frameIndex <= 4, `future event leaked: frame ${event.frameIndex}`);
    }
  });

  it("future marker positions are absent at T", () => {
    for (const marker of visibleMarkers(index, 4)) {
      assert.ok(marker.frameIndex <= 4, `future marker leaked: frame ${marker.frameIndex}`);
    }
  });

  it("future event counts are not revealed", () => {
    // At T only past structure is countable: nothing exposes the total.
    assert.equal(visibleEvents(index, 4).length, 0);
    assert.equal(olderEvents(index, 4).length, 0);
  });

  it("legitimate reveal at the boundary", () => {
    assert.ok(visibleEvents(index, 5).length > 0, "flag event reveals at its frame");
    assert.ok(visibleEvents(index, 5).every((e) => e.frameIndex <= 5));
  });
});

describe("future laps/sectors/compounds/stints never appear at T", () => {
  const corpus: TelemetryCorpus = {
    raceId: "R",
    laps: [
      lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: 95.0 }),
      // Future: faster lap, newer compound — must not move the reference.
      lap({ lapNumber: 11, observedAtS: 3000, lapTimeS: 90.0, compound: "SOFT" }),
    ],
    stints: [],
  };

  it("future completed lap hidden at T", () => {
    const out = selectCompletedDriverLaps(corpus, "HAM", 2000);
    assert.deepEqual(out.map((l) => l.lapNumber), [10]);
  });

  it("future lap cannot become the reference baseline", () => {
    const ref = selectReferenceLap(selectCompletedDriverLaps(corpus, "HAM", 2000));
    assert.equal(ref?.lapNumber, 10);
    assert.equal(ref?.lapTimeS, 95.0);
  });

  it("future stint structure hidden at T", () => {
    const history = selectStintHistory(corpus, "HAM", 2000, null, null, null);
    assert.equal(history.completed.length, 0);
  });

  it("legitimate reveal at the boundary", () => {
    const out = selectCompletedDriverLaps(corpus, "HAM", 3000);
    assert.deepEqual(out.map((l) => l.lapNumber), [10, 11]);
    assert.equal(selectReferenceLap(out)?.lapNumber, 11);
  });
});

describe("cross-state simulation identities never attach", () => {
  const frameA = {
    raceId: "2022-r01-R", frameIndex: 583,
    anchorDriverId: "perez", anchorLapNumber: 30, anchorStateTimeS: 6745.686,
  };
  const frameB = {
    raceId: "2022-r01-R", frameIndex: 584,
    anchorDriverId: "perez", anchorLapNumber: 30, anchorStateTimeS: 6746.1,
  };
  const entryB = {
    race_id: "2022-r01-R", anchor_driver_id: "perez",
    anchor_lap_number: 30, anchor_state_time_s: 6746.1,
    target_driver_id: "perez", master_seed: 20240101, simulation_count: 5000,
    supported: true, alternative_count: 9, comparison_identities: [], cache_key: "k",
  };

  it("state-B catalogue entry never matches state A", () => {
    const a = adaptDecisionTarget(frameA, "perez");
    assert.equal(a.ok, true);
    if (a.ok) assert.equal(matchStrategyEntry([entryB], a.anchor, a.targetDriverId), null);
  });

  it("state-B counterfactual domain never serves state A", () => {
    const drivers = [
      { driver_id: "perez", position: 4, decision_lap: 29, remaining_laps: 28, eligible_n_min: 1, eligible_n_max: 26, eligible: true, compound: "MEDIUM", status: "ACTIVE" },
    ];
    assert.equal(eligibleNDomain(drivers, "leclerc"), null);
    const b = adaptDecisionTarget(frameB, "perez");
    const a = adaptDecisionTarget(frameA, "perez");
    assert.equal(b.ok && a.ok, true);
    if (b.ok && a.ok) {
      assert.notDeepEqual(b.anchor, a.anchor);
    }
  });

  it("hooks verify response identity before display (source guard)", () => {
    const hook = readHook();
    assert.ok(
      hook.includes("response.anchor_state_time_s !== anchor.anchor_state_time_s"),
      "strategy response identity checked",
    );
    assert.ok(
      hook.includes("response.target_driver_id !== targetDriverId"),
      "strategy target identity checked",
    );
    assert.ok(hook.includes("requestId !== requestIdRef.current"), "stale run rejected");
    assert.ok(hook.includes("abortRef.current?.abort()"), "in-flight work aborted on move");
  });
});

// --- source guard helper (repo precedent: read own source, no React) ---
const HERE = dirname(fileURLToPath(import.meta.url));

function readHook(): string {
  return readFileSync(
    join(HERE, "..", "hooks", "useDecisionExploration.ts"),
    "utf8",
  );
}
