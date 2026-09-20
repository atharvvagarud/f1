import { strict as assert } from "node:assert";
import { beforeEach, describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { REPLAY_PAGE_SIZE, V2ApiError, fetchFullTimeline, getReplayFrame, getReplayPrediction, getReplayProbabilityTimeline, getReplayTimelinePage, getV2Races, validateTimeline, type FetchLike, type ReplayFrameMeta } from "./v2.ts";

// Characterisation tests for the V2 replay client (lib/v2.ts):
// endpoint URLs, pagination assembly + identity validation, error parsing.
// fetch is stubbed — no network, no server.
// Run with `node --test lib/v2.test.ts` (Node >= 22, no new dependencies).

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];
let routes: Map<string, { status: number; body: unknown }>;

function stubFetch() {
  calls = [];
  routes = new Map();
  const fetcher: FetchLike = async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const route = routes.get(url);
    if (!route) throw new Error(`unexpected fetch: ${url}`);
    return { ok: route.status >= 200 && route.status < 300, status: route.status, json: async () => route.body };
  };
  return fetcher;
}

const BASE = "http://127.0.0.1:8000";

function frame(raceId: string, index: number): ReplayFrameMeta {
  return {
    race_id: raceId,
    frame_index: index,
    anchor_driver_id: "alonso",
    anchor_lap_number: 28,
    anchor_state_time_s: 1000 + index,
    replay_contract_version: "v1",
  };
}

function timelinePage(raceId: string, total: number, offset: number, limit: number) {
  const frames: ReplayFrameMeta[] = [];
  for (let i = offset; i < Math.min(offset + limit, total); i++) frames.push(frame(raceId, i));
  return {
    race_id: raceId,
    replay_contract_version: "v1",
    total_frames: total,
    offset,
    limit,
    returned_count: frames.length,
    frames,
  };
}

describe("v2 client endpoints", () => {
  let fetcher: FetchLike;
  beforeEach(() => {
    fetcher = stubFetch();
  });

  it("getV2Races calls GET /v2/races on the default base", async () => {
    routes.set(`${BASE}/v2/races`, { status: 200, body: { races: [], count: 0 } });
    const data = await getV2Races(fetcher);
    assert.deepEqual(data, { races: [], count: 0 });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/v2/races");
  });

  it("getReplayTimelinePage encodes race and pagination", async () => {
    const page = timelinePage("2023-r01-R", 1091, 500, 500);
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/timeline?offset=500&limit=500`, {
      status: 200,
      body: page,
    });
    const data = await getReplayTimelinePage("2023-r01-R", 500, 500, fetcher);
    assert.equal(data.total_frames, 1091);
    assert.equal(data.frames[0].frame_index, 500);
  });

  it("getReplayFrame hits the factual frame route", async () => {
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/frames/428`, {
      status: 200,
      body: { frame: frame("2023-r01-R", 428) },
    });
    const data = await getReplayFrame("2023-r01-R", 428, fetcher);
    assert.equal(data.frame.frame_index, 428);
  });

  it("getReplayPrediction hits the cached prediction route", async () => {
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/predictions/0`, {
      status: 200,
      body: { cache_status: "HIT" },
    });
    const data = await getReplayPrediction("2023-r01-R", 0, fetcher);
    assert.equal(data.cache_status, "HIT");
  });

  it("unknown race surfaces 404 unknown_race", async () => {
    routes.set(`${BASE}/v2/races/2025-r01-R/replay/timeline?offset=0&limit=500`, {
      status: 404,
      body: { error: "unknown_race", detail: "no served replay race '2025-r01-R'" },
    });
    await assert.rejects(getReplayTimelinePage("2025-r01-R", 0, 500, fetcher), (error: unknown) => {
      assert.ok(error instanceof V2ApiError);
      assert.equal(error.status, 404);
      assert.equal(error.code, "unknown_race");
      return true;
    });
  });

  it("503 unavailable keeps reason; 404 not-checkpoint keeps pointers", async () => {
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/predictions/5`, {
      status: 503,
      body: { error: "prediction_unavailable", detail: "d", reason: "cache_missing" },
    });
    await assert.rejects(getReplayPrediction("2023-r01-R", 5, fetcher), (error: unknown) => {
      assert.ok(error instanceof V2ApiError);
      assert.ok(error.isUnavailable());
      assert.equal(error.reason, "cache_missing");
      return true;
    });
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/predictions/6`, {
      status: 404,
      body: {
        error: "not_prediction_checkpoint",
        detail: "d",
        previous_prediction_checkpoint_frame: 0,
        next_prediction_checkpoint_frame: 61,
      },
    });
    await assert.rejects(getReplayPrediction("2023-r01-R", 6, fetcher), (error: unknown) => {
      assert.ok(error instanceof V2ApiError);
      assert.ok(error.isNotCheckpoint());
      assert.equal(error.previousCheckpoint, 0);
      assert.equal(error.nextCheckpoint, 61);
      return true;
    });
  });
});

describe("timeline pagination assembly", () => {
  let fetcher: FetchLike;
  beforeEach(() => {
    fetcher = stubFetch();
  });

  it("assembles a multi-page race (1091 frames, 500/page) in order", async () => {
    const total = 1091;
    for (const offset of [0, 500, 1000]) {
      routes.set(
        `${BASE}/v2/races/2023-r01-R/replay/timeline?offset=${offset}&limit=${REPLAY_PAGE_SIZE}`,
        { status: 200, body: timelinePage("2023-r01-R", total, offset, REPLAY_PAGE_SIZE) },
      );
    }
    const frames = await fetchFullTimeline("2023-r01-R", fetcher);
    assert.equal(frames.length, total);
    assert.deepEqual(
      frames.map((f) => f.frame_index),
      Array.from({ length: total }, (_, i) => i),
    );
    assert.equal(calls.length, 3);
  });

  it("rejects a truncated page (missing frames are never inferred)", async () => {
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/timeline?offset=0&limit=500`, {
      status: 200,
      body: timelinePage("2023-r01-R", 1091, 0, 500),
    });
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/timeline?offset=500&limit=500`, {
      status: 200,
      body: { ...timelinePage("2023-r01-R", 1091, 500, 500), frames: [] },
    });
    await assert.rejects(fetchFullTimeline("2023-r01-R", fetcher), /truncated/);
  });

  it("issues exactly ceil(total/500) timeline requests (request budget)", async () => {
    for (const total of [1, 499, 500, 501, 1000, 2001]) {
      fetcher = stubFetch();
      const expected = Math.ceil(total / REPLAY_PAGE_SIZE);
      for (let offset = 0; offset < total; offset += REPLAY_PAGE_SIZE) {
        routes.set(
          `${BASE}/v2/races/2023-r01-R/replay/timeline?offset=${offset}&limit=${REPLAY_PAGE_SIZE}`,
          { status: 200, body: timelinePage("2023-r01-R", total, offset, REPLAY_PAGE_SIZE) },
        );
      }
      const frames = await fetchFullTimeline("2023-r01-R", fetcher);
      assert.equal(frames.length, total);
      assert.equal(calls.length, expected);
    }
  });

  it("rejects duplicates, gaps, and race mixing", () => {
    const good = [frame("2023-r01-R", 0), frame("2023-r01-R", 1)];
    assert.doesNotThrow(() => validateTimeline(good, 2, "2023-r01-R"));
    assert.throws(() => validateTimeline([good[0], good[0]], 2, "2023-r01-R"), /identity break/);
    assert.throws(() => validateTimeline([good[1]], 2, "2023-r01-R"), /incomplete/);
    assert.throws(() => validateTimeline(good, 3, "2023-r01-R"), /incomplete/);
    assert.throws(
      () => validateTimeline([frame("2021-r12-R", 0), frame("2021-r12-R", 1)], 2, "2023-r01-R"),
      /identity break/,
    );
  });

  it("race list passes served races through without client filtering", async () => {
    const body = {
      races: [{ race_id: "2023-r01-R", season: 2023, round_no: 1, event_name: "Bahrain Grand Prix" }],
      count: 1,
    };
    routes.set(`${BASE}/v2/races`, { status: 200, body });
    const data = await getV2Races(fetcher);
    assert.deepEqual(data, body); // backend is authority; no 2025 fabricated here
  });
});

describe("probability timeline client (R6)", () => {
  let fetcher: FetchLike;
  beforeEach(() => {
    fetcher = stubFetch();
  });

  it("hits the probability-timeline route and parses the payload", async () => {
    const timeline = {
      race_id: "2023-r01-R",
      replay_contract_version: "v1",
      prediction_contract_version: "v1",
      probability_timeline_contract_version: "v1",
      probability_semantics: "INDEPENDENT_BINARY",
      model: { probability_semantics: "INDEPENDENT_BINARY" },
      timeline_identity: "abc",
      checkpoints: [
        { frame_index: 10, state_time_s: 110, leader_lap: 1, reasons: ["LEADER_LAP"] },
      ],
      driver_series: [
        { driver_id: "alonso", points: [{ frame_index: 10, state_time_s: 110, leader_lap: 1, winner_probability: 0.6 }] },
        { driver_id: "bottas", points: [{ frame_index: 10, state_time_s: 110, leader_lap: 1, winner_probability: null }] },
      ],
    };
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/probability-timeline`, {
      status: 200,
      body: timeline,
    });
    const data = await getReplayProbabilityTimeline("2023-r01-R", fetcher);
    assert.equal(data.probability_semantics, "INDEPENDENT_BINARY");
    assert.equal(data.checkpoints[0].frame_index, 10);
    assert.equal(data.driver_series[1].points[0].winner_probability, null);
    assert.equal(calls[0].url, `${BASE}/v2/races/2023-r01-R/replay/probability-timeline`);
  });

  it("503 cache_missing is an unavailable error (nonfatal to caller)", async () => {
    routes.set(`${BASE}/v2/races/2023-r01-R/replay/probability-timeline`, {
      status: 503,
      body: { error: "prediction_unavailable", detail: "d", reason: "cache_missing" },
    });
    await assert.rejects(
      getReplayProbabilityTimeline("2023-r01-R", fetcher),
      (error: unknown) => {
        assert.ok(error instanceof V2ApiError);
        assert.ok(error.isUnavailable());
        assert.equal(error.reason, "cache_missing");
        return true;
      },
    );
  });
});
