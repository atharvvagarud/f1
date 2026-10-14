import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping; tsc without allowImportingTsExtensions cannot, hence the
// targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { buildEventIndex, categoryOf, nextEventFrame, nextLapFrame, olderEvents, previousEventFrame, previousLapFrame, recentEvents, visibleEvents, visibleMarkers } from "./events.ts";
import type { EventIndex, FrameDigest } from "./events.ts";

// Event model, exact mapping, ordering, and causal visibility (V3.10D).
// Run with `node --test events.test.ts` (Node >= 22, no new dependencies).

function digest(over: Partial<FrameDigest> = {}): FrameDigest {
  return {
    frameIndex: 0,
    anchorStateTimeS: 4405.562,
    leaderLap: 1,
    trackState: "all_clear",
    messageCategory: null,
    messageFlag: null,
    pits: {},
    ...over,
  };
}

function corpus(frames: FrameDigest[]): EventIndex {
  return buildEventIndex("2024-r21-R", frames.length, frames);
}

describe("event taxonomy", () => {
  it("uses a closed kind set with stable categories", () => {
    assert.equal(categoryOf("FLAG_SAFETY_CAR"), "FLAG");
    assert.equal(categoryOf("FLAG_UNKNOWN"), "FLAG");
    assert.equal(categoryOf("RC_MESSAGE"), "MESSAGE");
    assert.equal(categoryOf("PIT"), "PIT");
    assert.equal(categoryOf("LAP"), "LAP");
  });

  it("assigns stable deterministic IDs", () => {
    const index = corpus([
      digest({ frameIndex: 0 }),
      digest({ frameIndex: 1, trackState: "safety_car", anchorStateTimeS: 4410 }),
    ]);
    assert.equal(index.events.length, 1);
    assert.equal(
      index.events[0].id,
      "2024-r21-R:1:FLAG_SAFETY_CAR:-",
    );
  });
});

describe("exact mapping (first-observable-frame)", () => {
  it("frame 0 is baseline, never an event", () => {
    const index = corpus([digest({ frameIndex: 0, trackState: "yellow" })]);
    assert.equal(index.events.length, 0);
  });

  it("maps flag transitions to the first frame showing them", () => {
    const index = corpus([
      digest({ frameIndex: 0, trackState: "all_clear" }),
      digest({ frameIndex: 1, trackState: "all_clear" }),
      digest({ frameIndex: 2, trackState: "safety_car", leaderLap: 2 }),
      digest({ frameIndex: 3, trackState: "safety_car" }),
    ]);
    const flags = index.events.filter((e) => e.kind === "FLAG_SAFETY_CAR");
    assert.equal(flags.length, 1);
    assert.equal(flags[0].frameIndex, 2);
    assert.equal(flags[0].label, "SAFETY CAR");
  });

  it("maps message-pair changes without rewriting source text", () => {
    const index = corpus([
      digest({ frameIndex: 0 }),
      digest({
        frameIndex: 1,
        messageCategory: "Flag",
        messageFlag: "YELLOW",
      }),
      digest({
        frameIndex: 2,
        messageCategory: "Flag",
        messageFlag: "YELLOW",
      }),
    ]);
    const messages = index.events.filter((e) => e.kind === "RC_MESSAGE");
    assert.equal(messages.length, 1);
    assert.equal(messages[0].frameIndex, 1);
    assert.equal(messages[0].label, "Flag · YELLOW");
  });

  it("maps pit-count increments per driver", () => {
    const index = corpus([
      digest({ frameIndex: 0, pits: { norris: 0 } }),
      digest({ frameIndex: 1, pits: { norris: 0 } }),
      digest({ frameIndex: 2, pits: { norris: 1 } }),
    ]);
    const pits = index.events.filter((e) => e.kind === "PIT");
    assert.equal(pits.length, 1);
    assert.equal(pits[0].frameIndex, 2);
    assert.equal(pits[0].driverId, "norris");
    assert.ok(pits[0].label.includes("NORRIS"));
  });

  it("rejects pits claimed from an unknown baseline instead of placing them", () => {
    const index = corpus([
      digest({ frameIndex: 0, pits: {} }),
      digest({ frameIndex: 1, pits: { norris: 1 } }),
    ]);
    assert.equal(index.events.filter((e) => e.kind === "PIT").length, 0);
    assert.equal(index.rejected.length, 1);
    assert.equal(index.rejected[0].reason, "pit-from-unknown");
  });

  it("ignores first-observed zero counts silently", () => {
    const index = corpus([
      digest({ frameIndex: 0, pits: {} }),
      digest({ frameIndex: 1, pits: { norris: 0 } }),
      digest({ frameIndex: 2, pits: { norris: 1 } }),
    ]);
    assert.equal(index.rejected.length, 0);
    assert.equal(index.events.filter((e) => e.kind === "PIT").length, 1);
  });

  it("maps lap increments to the first frame of the lap", () => {
    const index = corpus([
      digest({ frameIndex: 0, leaderLap: 1 }),
      digest({ frameIndex: 1, leaderLap: 1 }),
      digest({ frameIndex: 2, leaderLap: 2 }),
    ]);
    assert.deepEqual(index.lapStarts, [2]);
    const laps = index.events.filter((e) => e.kind === "LAP");
    assert.equal(laps.length, 1);
    assert.equal(laps[0].label, "LAP 2");
  });

  it("fails loudly on a gapped corpus instead of deriving across it", () => {
    assert.throws(() =>
      buildEventIndex("2024-r21-R", 3, [
        digest({ frameIndex: 0 }),
        digest({ frameIndex: 2 }),
      ]),
    );
  });
});

describe("deterministic ordering", () => {
  it("orders by frame, then FLAG/MESSAGE/PIT/driver/LAP derivation order", () => {
    const index = corpus([
      digest({ frameIndex: 0, trackState: "all_clear", pits: { a: 0, b: 0 } }),
      digest({
        frameIndex: 1,
        trackState: "yellow",
        messageCategory: "Flag",
        messageFlag: "YELLOW",
        leaderLap: 2,
        pits: { a: 1, b: 1 },
      }),
    ]);
    const kinds = index.events.map((e) => e.kind);
    assert.deepEqual(kinds, [
      "FLAG_YELLOW",
      "RC_MESSAGE",
      "PIT",
      "PIT",
      "LAP",
    ]);
    assert.deepEqual(
      index.events.filter((e) => e.kind === "PIT").map((e) => e.driverId),
      ["a", "b"],
    );
  });

  it("aggregates same-frame markers deterministically without dropping", () => {
    const index = corpus([
      digest({ frameIndex: 0, trackState: "all_clear", pits: { a: 0 } }),
      digest({ frameIndex: 1, trackState: "yellow", pits: { a: 1 } }),
    ]);
    const markers = visibleMarkers(index, 1);
    assert.equal(markers.length, 1);
    assert.equal(markers[0].count, 2);
    assert.equal(markers[0].events.length, 2);
    assert.deepEqual(markers[0].kinds, ["FLAG_YELLOW", "PIT"]);
  });
});

describe("causal visibility", () => {
  function race(): EventIndex {
    return corpus([
      digest({ frameIndex: 0, trackState: "all_clear", pits: { norris: 0 } }),
      digest({ frameIndex: 1, trackState: "safety_car", pits: { norris: 0 } }),
      digest({
        frameIndex: 2,
        trackState: "safety_car",
        pits: { norris: 0 },
        messageCategory: "SafetyCar",
        messageFlag: "DEPLOYED",
      }),
      digest({ frameIndex: 3, trackState: "all_clear", pits: { norris: 1 } }),
      digest({ frameIndex: 4, trackState: "all_clear", pits: { norris: 1 } }),
    ]);
  }

  it("shows only events at or before T", () => {
    const index = race();
    assert.deepEqual(
      visibleEvents(index, 0).map((e) => e.frameIndex),
      [],
    );
    assert.deepEqual(
      visibleEvents(index, 1).map((e) => e.frameIndex),
      [1],
    );
    assert.deepEqual(
      visibleEvents(index, 4).map((e) => e.frameIndex),
      [1, 2, 3, 3],
    );
  });

  it("bounds the L0 feed to the latest N causal events", () => {
    const index = race();
    assert.equal(recentEvents(index, 4, 2).length, 2);
    assert.equal(olderEvents(index, 4, 2).length, 2);
    assert.equal(recentEvents(index, 0, 5).length, 0);
  });

  it("markers never include future frames", () => {
    const index = race();
    assert.deepEqual(
      visibleMarkers(index, 2).map((m) => m.frameIndex),
      [1, 2],
    );
  });
});

describe("event navigation", () => {
  function race(): EventIndex {
    return corpus([
      digest({ frameIndex: 0 }),
      digest({ frameIndex: 1, trackState: "yellow" }),
      digest({ frameIndex: 2, trackState: "yellow" }),
      digest({ frameIndex: 3, trackState: "all_clear" }),
    ]);
  }

  it("previous event resolves strictly before T", () => {
    const index = race();
    assert.equal(previousEventFrame(index, 0), null);
    assert.equal(previousEventFrame(index, 1), null);
    assert.equal(previousEventFrame(index, 3), 1);
    assert.equal(previousEventFrame(index, 4), 3);
  });

  it("next event returns a frame only — no future identity", () => {
    const index = race();
    const next: number | null = nextEventFrame(index, 0);
    assert.equal(next, 1);
    assert.equal(nextEventFrame(index, 3), null);
    // The return type carries no kind, label, driver, or count.
    const asText = JSON.stringify(nextEventFrame(index, 2));
    assert.equal(asText, "3");
  });

  it("lap navigation resolves to exact first-frames without a lap clock", () => {
    const index = corpus([
      digest({ frameIndex: 0, leaderLap: 1 }),
      digest({ frameIndex: 1, leaderLap: 1 }),
      digest({ frameIndex: 2, leaderLap: 2 }),
      digest({ frameIndex: 3, leaderLap: 3 }),
    ]);
    assert.equal(previousLapFrame(index, 3), 2);
    assert.equal(previousLapFrame(index, 2), null);
    assert.equal(nextLapFrame(index, 0), 2);
    assert.equal(nextLapFrame(index, 3), null);
  });
});

describe("performance (representative corpus)", () => {
  it("derives + queries a max-size corpus well within budget", () => {
    const N = 1532;
    const frames: FrameDigest[] = [];
    let lap = 1;
    for (let i = 0; i < N; i++) {
      if (i > 0 && i % 22 === 0) lap += 1;
      frames.push(
        digest({
          frameIndex: i,
          anchorStateTimeS: 4405 + i * 4,
          leaderLap: lap,
          trackState: i === 400 ? "safety_car" : i === 460 ? "all_clear" : "all_clear",
          messageCategory: i === 400 ? "SafetyCar" : null,
          messageFlag: i === 400 ? "DEPLOYED" : null,
          pits: { norris: i >= 700 ? 1 : 0, verstappen: i >= 900 ? 1 : 0 },
        }),
      );
    }
    const t0 = Date.now();
    const index = corpus(frames);
    const buildMs = Date.now() - t0;
    const t1 = Date.now();
    for (let t = 0; t < N; t += 7) {
      visibleEvents(index, t);
      visibleMarkers(index, t);
      previousEventFrame(index, t);
      nextEventFrame(index, t);
    }
    const queryMs = Date.now() - t1;
    assert.ok(index.events.length > 50, "representative event volume");
    assert.ok(buildMs < 1000, `single-pass build: ${buildMs}ms`);
    assert.ok(queryMs < 1000, `prefix lookups: ${queryMs}ms`);
  });
});
describe("temporal poison tests (mandatory)", () => {
  function poisoned(): EventIndex {
    // T=1 observer; frames 2+ carry a future SC, message, pit, retirement-like
    // flag storm. None may leak through any causal selector at T=1.
    return corpus([
      digest({ frameIndex: 0, trackState: "all_clear", pits: { norris: 0 } }),
      digest({ frameIndex: 1, trackState: "all_clear", pits: { norris: 0 } }),
      digest({
        frameIndex: 2,
        trackState: "safety_car",
        messageCategory: "SafetyCar",
        messageFlag: "DEPLOYED",
        pits: { norris: 1 },
      }),
      digest({ frameIndex: 3, trackState: "red_flag" }),
    ]);
  }

  it("future SC, message, pit, and flag leak through nothing at T", () => {
    const index = poisoned();
    assert.equal(visibleEvents(index, 1).length, 0);
    assert.equal(recentEvents(index, 1).length, 0);
    assert.equal(olderEvents(index, 1).length, 0);
    assert.equal(visibleMarkers(index, 1).length, 0);
  });

  it("future counts and positions stay hidden", () => {
    const index = poisoned();
    assert.equal(previousEventFrame(index, 1), null);
    // nextEventFrame may point forward (navigation), but reveals no identity:
    const next = nextEventFrame(index, 1);
    assert.equal(next, 2);
    assert.equal(typeof next, "number");
  });

  it("events appear exactly when their frame is reached", () => {
    const index = poisoned();
    assert.equal(visibleEvents(index, 2).length, 3);
    assert.equal(visibleEvents(index, 3).length, 4);
    assert.deepEqual(
      visibleMarkers(index, 3).map((m) => m.frameIndex),
      [2, 3],
    );
  });
});
