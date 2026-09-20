import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { BASE_INTERVAL_MS, canGoNext, canGoPrevious, compareRaces, displayFrame, driverStatusOf, evictOldest, firstIndex, formatAge, formatGapSeconds, formatLap, formatProbability, formatRaceTime, frameIdentityOf, intervalForSpeed, isCurrentResponse, lastIndex, leaderLapSearchStep, nextIndex, playbackReducer, previousIndex, sumProbabilities, type PlaybackState } from "./replayMachine.ts";

// Pure-logic tests for the replay feature (features/replay/lib).
// Run with `node --test features/replay/lib/replayMachine.test.ts`.

const fresh = (over: Partial<PlaybackState> = {}): PlaybackState => ({
  status: "paused",
  speed: 1,
  index: 0,
  totalFrames: 1091,
  ...over,
});

describe("navigation bounds", () => {
  it("first/previous/next/last clamp without wraparound", () => {
    assert.equal(firstIndex(), 0);
    assert.equal(lastIndex(1091), 1090);
    assert.equal(previousIndex(0), 0);
    assert.equal(previousIndex(5), 4);
    assert.equal(nextIndex(5, 1091), 6);
    assert.equal(nextIndex(1090, 1091), 1090);
    assert.equal(canGoPrevious(0), false);
    assert.equal(canGoPrevious(1), true);
    assert.equal(canGoNext(1090, 1091), false);
    assert.equal(canGoNext(1089, 1091), true);
    assert.equal(displayFrame(0), 1); // 1-based display, 0-based identity
    assert.equal(displayFrame(427), 428);
  });
});

describe("playback reducer", () => {
  it("play/pause toggle with end-of-race guard", () => {
    assert.equal(playbackReducer(fresh(), { type: "play" }).status, "playing");
    assert.equal(
      playbackReducer(fresh({ status: "playing" }), { type: "pause" }).status,
      "paused",
    );
    // At the last frame there is nothing ahead: play stays paused.
    assert.equal(
      playbackReducer(fresh({ index: 1090 }), { type: "play" }).status,
      "paused",
    );
  });

  it("manual seek pauses deterministically and clamps", () => {
    const moved = playbackReducer(fresh({ status: "playing", index: 10 }), {
      type: "seek",
      index: 400,
    });
    assert.equal(moved.status, "paused");
    assert.equal(moved.index, 400);
    assert.equal(playbackReducer(fresh(), { type: "seek", index: 99999 }).index, 1090);
    assert.equal(playbackReducer(fresh(), { type: "seek", index: -5 }).index, 0);
  });

  it("tick advances once and auto-pauses at the end without wrap", () => {
    const advanced = playbackReducer(fresh({ status: "playing", index: 7 }), { type: "tick" });
    assert.equal(advanced.index, 8);
    assert.equal(advanced.status, "playing");
    const ended = playbackReducer(fresh({ status: "playing", index: 1090 }), { type: "tick" });
    assert.equal(ended.index, 1090);
    assert.equal(ended.status, "paused");
    const paused = playbackReducer(fresh({ index: 7 }), { type: "tick" });
    assert.equal(paused.index, 7); // paused ticks are no-ops
  });

  it("race change resets to frame 0 paused; speed is selectable", () => {
    const reset = playbackReducer(fresh({ status: "playing", index: 500 }), {
      type: "reset",
      totalFrames: 60,
    });
    assert.deepEqual(reset, { status: "paused", speed: 1, index: 0, totalFrames: 60 });
    assert.equal(playbackReducer(fresh(), { type: "setSpeed", speed: 4 }).speed, 4);
    assert.equal(intervalForSpeed(1), BASE_INTERVAL_MS);
    assert.equal(intervalForSpeed(0.5), BASE_INTERVAL_MS * 2);
    assert.equal(intervalForSpeed(4), Math.round(BASE_INTERVAL_MS / 4));
  });
});

describe("leader-lap search mapping", () => {
  it("binary search finds the first frame reaching the lap", () => {
    // Leader laps 1..57 over 1091 frames: lap L starts at frame (L-1)*19.
    const laps = Array.from({ length: 1091 }, (_, i) => Math.floor(i / 19) + 1);
    const probes = laps.map((leaderLap, frameIndex) => ({ frameIndex, leaderLap }));
    // Simulate sparse probing: keep only endpoints, walk the search.
    const sparse = [probes[0], probes[1090]];
    for (;;) {
      const decision = leaderLapSearchStep(sparse, 1091, 20);
      if (decision.done) {
        assert.equal(decision.found, 19 * 19); // lap 20 starts at frame 361
        break;
      }
      sparse.push(probes[decision.probe]);
    }
  });

  it("unreachable laps and unknown/null laps resolve to no frame", () => {
    const full = Array.from({ length: 60 }, (_, frameIndex) => ({
      frameIndex,
      leaderLap: Math.min(3, Math.floor(frameIndex / 20) + 1),
    }));
    assert.deepEqual(leaderLapSearchStep(full, 60, 4), { done: true, found: null });
    assert.deepEqual(leaderLapSearchStep(full, 60, 0), { done: true, found: null });
    assert.deepEqual(
      leaderLapSearchStep([{ frameIndex: 0, leaderLap: null }], 60, 1),
      { done: true, found: null }, // never guess through unknowns
    );
  });

  it("sparse probes request the midpoint instead of guessing", () => {
    const decision = leaderLapSearchStep(
      [
        { frameIndex: 0, leaderLap: 1 },
        { frameIndex: 59, leaderLap: 3 },
      ],
      60,
      4,
    );
    assert.equal(decision.done, false);
    if (!decision.done) assert.ok(decision.probe > 0 && decision.probe < 59);
  });
});

describe("factual formatting", () => {
  it("gaps, laps, times, ages render without fabricating zeros", () => {
    assert.equal(formatGapSeconds(1.23456), "+1.235");
    assert.equal(formatGapSeconds(null), "—");
    assert.equal(formatLap(28), "L28");
    assert.equal(formatLap(null), "—");
    assert.equal(formatRaceTime(2974.257), "49:34.257");
    assert.equal(formatRaceTime(null), "—");
    assert.equal(formatAge(0.0), "live");
    assert.equal(formatAge(48.2), "stale 48.2s");
    assert.equal(formatAge(null), "");
  });

  it("probabilities pass through; null stays null (never 0%)", () => {
    assert.equal(formatProbability(0.04086444508464821), "4.09%");
    assert.equal(formatProbability(null), null);
    // Sums >100% are valid under INDEPENDENT_BINARY and preserved.
    assert.ok(sumProbabilities([0.5, 0.4, 0.3]) > 1);
    assert.equal(sumProbabilities([0.5, null, 0.25]), 0.75);
  });

  it("driver status distinguishes observed / stale / unobserved", () => {
    assert.equal(driverStatusOf({ observable: true, observation_age_s: 0.0 }), "observed");
    assert.equal(driverStatusOf({ observable: true, observation_age_s: 48.2 }), "stale");
    assert.equal(driverStatusOf({ observable: false, observation_age_s: null }), "unobserved");
  });

  it("frame identity is race + 0-based index only", () => {
    assert.deepEqual(
      frameIdentityOf({ frame: { race_id: "2023-r01-R", frame_index: 428 } } as never),
      { raceId: "2023-r01-R", frameIndex: 428 },
    );
  });

  it("served races sort chronologically", () => {
    const rows = [
      { season: 2023, round_no: 1, race_id: "2023-r01-R" },
      { season: 2021, round_no: 12, race_id: "2021-r12-R" },
      { season: 2023, round_no: 2, race_id: "2023-r02-R" },
    ];
    assert.deepEqual([...rows].sort(compareRaces).map((r) => r.race_id), [
      "2021-r12-R",
      "2023-r01-R",
      "2023-r02-R",
    ]);
  });
});

describe("bounded frame cache (R7-O)", () => {
  it("enforces the 200-entry bound with deterministic oldest-first eviction", () => {
    const cache = new Map<number, number>();
    for (let i = 0; i < 250; i++) {
      cache.set(i, i);
      evictOldest(cache, 200);
    }
    assert.equal(cache.size, 200);
    assert.equal(cache.has(0), false); // oldest evicted
    assert.equal(cache.has(49), false);
    assert.equal(cache.has(50), true);
    assert.equal(cache.has(249), true);
    assert.deepEqual([...cache.keys()], Array.from({ length: 200 }, (_, i) => i + 50));
  });

  it("leaves a cache below the bound untouched", () => {
    const cache = new Map<number, number>([[1, 1], [2, 2]]);
    evictOldest(cache, 200);
    assert.deepEqual([...cache.keys()], [1, 2]);
  });

  it("isolates a rebuilt cache (race change clears entries)", () => {
    const cache = new Map<number, number>([[1, 1]]);
    evictOldest(cache, 0);
    assert.equal(cache.size, 0);
  });
});

describe("stale-response suppression (R7-M)", () => {
  it("accepts only the active session + request generation", () => {
    assert.equal(isCurrentResponse(3, 3, 1, 1), true);
    // A newer frame navigation bumped the request id.
    assert.equal(isCurrentResponse(3, 4, 1, 1), false);
    // A race change bumped the session.
    assert.equal(isCurrentResponse(3, 3, 1, 2), false);
    assert.equal(isCurrentResponse(3, 3, 2, 1), false);
  });
});
