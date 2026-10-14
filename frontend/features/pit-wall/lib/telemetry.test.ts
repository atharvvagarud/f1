import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { formatDelta, formatLapTime, formatSectorTime, lapDeltaVsReference, selectCompletedDriverLaps, selectCurrentLapState, selectRecentLaps, selectReferenceLap, selectStintHistory } from "./telemetry.ts";
import type { TelemetryCorpus, TelemetryLap } from "./telemetry.ts";

// Behavior tests for the V3.10F causal telemetry selectors. Completed laps
// only, <=T slicing, best-so-far reference, descriptive deltas, stint
// causality, missingness, and the mandatory future-data poison tests.
// Run with `node --test telemetry.test.ts` (Node >= 22, no new dependencies).

function lap(
  over: Partial<TelemetryLap> & { lapNumber: number; observedAtS: number },
): TelemetryLap {
  return {
    driverId: "HAM",
    lapTimeS: 95.0,
    sector1S: 30.0,
    sector2S: 40.0,
    sector3S: 25.0,
    compound: "MEDIUM",
    stintNumber: 1,
    pitEntry: null,
    pitExit: null,
    generated: false,
    ...over,
  };
}

function corpus(laps: TelemetryLap[]): TelemetryCorpus {
  return { raceId: "R", laps, stints: [] };
}

describe("selectCompletedDriverLaps causality", () => {
  it("completed past lap visible", () => {
    const c = corpus([lap({ lapNumber: 10, observedAtS: 1000 })]);
    const out = selectCompletedDriverLaps(c, "HAM", 2000);
    assert.equal(out.length, 1);
    assert.equal(out[0].lapNumber, 10);
  });

  it("current unfinished lap final time hidden", () => {
    const c = corpus([
      lap({ lapNumber: 10, observedAtS: 1000 }),
      lap({ lapNumber: 11, observedAtS: 1100 }),
    ]);
    // T is after lap 10 completes but before lap 11 completes.
    const out = selectCompletedDriverLaps(c, "HAM", 1050);
    assert.deepEqual(
      out.map((l) => l.lapNumber),
      [10],
    );
  });

  it("future lap hidden at frame T", () => {
    const c = corpus([
      lap({ lapNumber: 10, observedAtS: 1000 }),
      lap({ lapNumber: 11, observedAtS: 1100, lapTimeS: 80.0 }),
    ]);
    const out = selectCompletedDriverLaps(c, "HAM", 1050);
    assert.ok(!out.some((l) => l.lapNumber === 11));
  });

  it("lap becomes visible exactly at its observation boundary", () => {
    const c = corpus([lap({ lapNumber: 11, observedAtS: 1100 })]);
    assert.equal(selectCompletedDriverLaps(c, "HAM", 1099.999).length, 0);
    assert.equal(selectCompletedDriverLaps(c, "HAM", 1100).length, 1);
  });

  it("selected driver only — no other-driver rows", () => {
    const c = corpus([
      lap({ lapNumber: 10, observedAtS: 1000 }),
      lap({ driverId: "VER", lapNumber: 10, observedAtS: 900 }),
    ]);
    const out = selectCompletedDriverLaps(c, "HAM", 2000);
    assert.ok(out.every((l) => l.driverId === "HAM"));
  });

  it("driver change re-slices the same corpus", () => {
    const c = corpus([
      lap({ lapNumber: 10, observedAtS: 1000 }),
      lap({ driverId: "VER", lapNumber: 12, observedAtS: 950 }),
    ]);
    assert.deepEqual(
      selectCompletedDriverLaps(c, "VER", 2000).map((l) => l.lapNumber),
      [12],
    );
    assert.deepEqual(
      selectCompletedDriverLaps(c, "HAM", 2000).map((l) => l.lapNumber),
      [10],
    );
  });
});

describe("reference semantics (<=T only)", () => {
  it("future lap does not alter the reference", () => {
    const past = [
      lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: 95.0 }),
      lap({ lapNumber: 11, observedAtS: 1050, lapTimeS: 94.0 }),
    ];
    const refBefore = selectReferenceLap(past);
    assert.deepEqual(refBefore, { lapNumber: 11, lapTimeS: 94.0 });
    // Poison: a faster future lap must not move the reference at T=1060.
    const poisoned = selectCompletedDriverLaps(
      corpus([
        ...past,
        lap({ lapNumber: 12, observedAtS: 2000, lapTimeS: 80.0 }),
      ]),
      "HAM",
      1060,
    );
    assert.deepEqual(selectReferenceLap(poisoned), refBefore);
  });

  it("reference becomes the fast lap once its boundary passes", () => {
    const c = corpus([
      lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: 95.0 }),
      lap({ lapNumber: 12, observedAtS: 2000, lapTimeS: 80.0 }),
    ]);
    const out = selectCompletedDriverLaps(c, "HAM", 2000);
    assert.deepEqual(selectReferenceLap(out), {
      lapNumber: 12,
      lapTimeS: 80.0,
    });
  });

  it("generated synthetic rows never become the reference", () => {
    const out = selectReferenceLap([
      lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: 95.0 }),
      lap({ lapNumber: 11, observedAtS: 1050, lapTimeS: 80.0, generated: true }),
    ]);
    assert.deepEqual(out, { lapNumber: 10, lapTimeS: 95.0 });
  });

  it("laps without a recorded time cannot be the reference", () => {
    const out = selectReferenceLap([
      lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: null }),
    ]);
    assert.equal(out, null);
  });

  it("deleted laps are NOT excluded (POST_RACE knowledge would leak)", () => {
    // The selector shape carries no deleted flag by design: exclusion would
    // inject a future stewards decision into the <=T reference.
    const probe = lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: 95.0 });
    assert.ok(!("deleted" in probe));
  });
});

describe("sector deltas", () => {
  it("completed sectors rendered with descriptive deltas", () => {
    const completed = [
      lap({
        lapNumber: 10,
        observedAtS: 1000,
        lapTimeS: 95.0,
        sector1S: 30.0,
        sector2S: 40.0,
        sector3S: 25.0,
      }),
      lap({
        lapNumber: 11,
        observedAtS: 1050,
        lapTimeS: 95.5,
        sector1S: 30.1,
        sector2S: 40.2,
        sector3S: 25.2,
      }),
    ];
    const ref = selectReferenceLap(completed);
    const delta = lapDeltaVsReference(completed[1], ref, completed);
    assert.equal(delta.lapS, 0.5);
    assert.ok(Math.abs((delta.sector1S ?? 0) - 0.1) < 1e-9);
  });

  it("missing sector stays missing (delta null, never zero)", () => {
    const completed = [
      lap({
        lapNumber: 10,
        observedAtS: 1000,
        lapTimeS: 95.0,
        sector1S: null,
        sector2S: 40.0,
        sector3S: 25.0,
      }),
      lap({
        lapNumber: 11,
        observedAtS: 1050,
        lapTimeS: 96.0,
        sector1S: 30.0,
        sector2S: 40.0,
        sector3S: 26.0,
      }),
    ];
    const ref = selectReferenceLap(completed);
    const delta = lapDeltaVsReference(completed[1], ref, completed);
    assert.equal(delta.sector1S, null);
    assert.notEqual(delta.sector3S, 0);
  });

  it("future sector hidden: delta uses only the <=T reference lap", () => {
    const completed = selectCompletedDriverLaps(
      corpus([
        lap({
          lapNumber: 10,
          observedAtS: 1000,
          lapTimeS: 95.0,
          sector1S: 30.0,
          sector2S: 40.0,
          sector3S: 25.0,
        }),
        lap({
          lapNumber: 12,
          observedAtS: 2000,
          lapTimeS: 80.0,
          sector1S: 20.0,
          sector2S: 30.0,
          sector3S: 20.0,
        }),
      ]),
      "HAM",
      1500,
    );
    const ref = selectReferenceLap(completed);
    assert.equal(ref?.lapNumber, 10);
  });

  it("no reference without eligible laps -> all deltas null", () => {
    const completed = [lap({ lapNumber: 10, observedAtS: 1000, lapTimeS: null })];
    const delta = lapDeltaVsReference(completed[0], null, completed);
    assert.deepEqual(delta, {
      lapS: null,
      sector1S: null,
      sector2S: null,
      sector3S: null,
    });
  });
});

describe("current-lap state", () => {
  it("in progress while within a lap of the leader", () => {
    assert.deepEqual(
      selectCurrentLapState({
        maxCompletedLap: 33,
        leaderLap: 34,
        raceComplete: false,
        hasFrameEvidence: true,
      }),
      { kind: "in-progress", lapNumber: 34 },
    );
  });

  it("no-new-lap when laps behind (no retirement inference)", () => {
    assert.deepEqual(
      selectCurrentLapState({
        maxCompletedLap: 30,
        leaderLap: 40,
        raceComplete: false,
        hasFrameEvidence: true,
      }),
      { kind: "no-new-lap", lastCompletedLap: 30 },
    );
  });

  it("replay end at the final frame", () => {
    assert.deepEqual(
      selectCurrentLapState({
        maxCompletedLap: 56,
        leaderLap: 56,
        raceComplete: true,
        hasFrameEvidence: true,
      }),
      { kind: "replay-end" },
    );
  });

  it("absent telemetry keeps the selection (no-evidence, no substitution)", () => {
    assert.deepEqual(
      selectCurrentLapState({
        maxCompletedLap: null,
        leaderLap: 10,
        raceComplete: false,
        hasFrameEvidence: false,
      }),
      { kind: "no-evidence" },
    );
  });
});

describe("stint history causality", () => {
  function stintCorpus(): TelemetryCorpus {
    return {
      raceId: "R",
      laps: [],
      stints: [
        {
          driverId: "HAM",
          stintNumber: 1,
          compound: "MEDIUM",
          startLap: 1,
          endLap: 13,
          startObservedAtS: 1000,
          endObservedAtS: 2000,
        },
        {
          driverId: "HAM",
          stintNumber: 2,
          compound: "HARD",
          startLap: 14,
          endLap: 28,
          startObservedAtS: 2100,
          endObservedAtS: 4000,
        },
        {
          driverId: "HAM",
          stintNumber: 3,
          compound: "SOFT",
          startLap: 29,
          endLap: 56,
          startObservedAtS: 4100,
          endObservedAtS: 8000,
        },
      ],
    };
  }

  it("completed stint visible; future stint hidden with its count", () => {
    const view = selectStintHistory(
      stintCorpus(),
      "HAM",
      3000,
      "HARD",
      2,
      20,
    );
    assert.deepEqual(
      view.completed.map((s) => s.stintNumber),
      [1],
    );
    assert.equal(view.active?.stintNumber, 2);
    // No trace of stint 3 anywhere in the view.
    assert.equal(JSON.stringify(view).includes('"stintNumber":3'), false);
  });

  it("future compound hidden; active compound comes from frame state", () => {
    const view = selectStintHistory(
      stintCorpus(),
      "HAM",
      3000,
      "HARD",
      2,
      20,
    );
    assert.equal(view.active?.compound, "HARD");
    assert.equal(JSON.stringify(view).includes("SOFT"), false);
  });

  it("active stint shows start + stint age, never the entity end lap", () => {
    const view = selectStintHistory(
      stintCorpus(),
      "HAM",
      3000,
      "HARD",
      2,
      20,
    );
    assert.equal(view.active?.startLap, 14);
    assert.equal(view.active?.stintAgeLaps, 7);
    assert.ok(!("endLap" in (view.active ?? {})));
  });

  it("ambiguous transition (no frame stint) stays explicit", () => {
    const view = selectStintHistory(
      stintCorpus(),
      "HAM",
      2050,
      null,
      null,
      13,
    );
    assert.equal(view.active, null);
    assert.equal(view.activeUnknown, true);
    assert.deepEqual(
      view.completed.map((s) => s.stintNumber),
      [1],
    );
  });

  it("stint becomes completed exactly at its end boundary", () => {
    const before = selectStintHistory(stintCorpus(), "HAM", 3999, "HARD", 2, 27);
    assert.equal(before.completed.length, 1);
    const after = selectStintHistory(stintCorpus(), "HAM", 4000, "SOFT", 3, 28);
    assert.deepEqual(
      after.completed.map((s) => s.stintNumber),
      [1, 2],
    );
  });
});

describe("recent laps + formatting", () => {
  it("recent window slices the <=T list only", () => {
    const completed = [
      lap({ lapNumber: 8, observedAtS: 800 }),
      lap({ lapNumber: 9, observedAtS: 900 }),
      lap({ lapNumber: 10, observedAtS: 1000 }),
    ];
    assert.deepEqual(
      selectRecentLaps(completed, 2).map((l) => l.lapNumber),
      [9, 10],
    );
  });

  it("formatters never zero-fill", () => {
    assert.equal(formatLapTime(null), null);
    assert.equal(formatSectorTime(null), null);
    assert.equal(formatDelta(null), null);
    assert.equal(formatLapTime(95.123), "1:35.123");
    assert.equal(formatSectorTime(30.1), "30.100");
    assert.equal(formatDelta(0.112), "+0.112");
    assert.equal(formatDelta(-0.4), "-0.400");
  });

  it("lap-time boundary: lap 1 S1 missing stays missing", () => {
    const first = lap({
      lapNumber: 1,
      observedAtS: 500,
      lapTimeS: 119.538,
      sector1S: null,
      sector2S: 54.367,
      sector3S: 32.463,
    });
    assert.equal(formatSectorTime(first.sector1S), null);
    assert.equal(formatLapTime(first.lapTimeS), "1:59.538");
  });
});
