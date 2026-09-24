import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  V2ApiError,
  isStrategyRequestInvalid,
  postStrategyCompare,
  type FetchLike,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./v2.ts";

// V2 strategy client (lib/v2.ts): POST payload/URL, response pass-through,
// and the stable 422 strategy_request_invalid contract. fetch is stubbed.

const BASE = "http://127.0.0.1:8000";
const URL = `${BASE}/v2/strategies/compare`;

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
    return {
      ok: route.status >= 200 && route.status < 300,
      status: route.status,
      json: async () => route.body,
    };
  };
  return fetcher;
}

const request = {
  race_id: "2022-r01-R",
  anchor_driver_id: "perez",
  anchor_lap_number: 30,
  anchor_state_time_s: 6745.686,
  target_driver_id: "perez",
  objective: "MAXIMIZE_WIN_PROBABILITY" as const,
  simulation_count: 1000,
  candidates: [{ action: "STAY_OUT" as const }],
};

const body = {
  strategy_contract_version: "s1",
  comparison_version: "v1",
  race_id: "2022-r01-R",
  target_driver_id: "perez",
  simulation_count: 1000,
  master_seed: 20240101,
  objective: "MAXIMIZE_WIN_PROBABILITY",
  metric: "WIN_PROBABILITY",
  probability_semantics: "MONTE_CARLO_FREQUENCY",
  supported: true,
  baseline: {
    valid_simulations: 1000,
    win_probability: 0.05,
    podium_probability: 0.2,
    expected_finish: 7.5,
    finish_position_distribution: [],
  },
  candidates: [],
  comparison_identity: "abc",
  limitations: [],
};

describe("postStrategyCompare", () => {
  it("posts the exact-anchor comparison payload", async () => {
    const fetcher = stubFetch();
    routes.set(URL, { status: 200, body });
    const response = await postStrategyCompare(request, fetcher, BASE);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, URL);
    assert.equal(calls[0].init?.method, "POST");
    const sent = JSON.parse(calls[0].init?.body as string);
    assert.equal(sent.race_id, "2022-r01-R");
    assert.equal(sent.target_driver_id, "perez");
    assert.equal(sent.objective, "MAXIMIZE_WIN_PROBABILITY");
    assert.equal(sent.simulation_count, 1000);
    assert.equal(response.probability_semantics, "MONTE_CARLO_FREQUENCY");
    assert.equal(response.supported, true);
  });

  it("passes the compact response through verbatim", async () => {
    const fetcher = stubFetch();
    routes.set(URL, { status: 200, body });
    const response = await postStrategyCompare(request, fetcher, BASE);
    assert.equal(response.comparison_identity, "abc");
    assert.equal(response.baseline?.expected_finish, 7.5);
  });

  it("surfaces validation failures as V2ApiError", async () => {
    const fetcher = stubFetch();
    routes.set(URL, {
      status: 422,
      body: {
        error: "strategy_request_invalid",
        reason: "duplicate_candidates",
        detail: "dup",
      },
    });
    await assert.rejects(
      postStrategyCompare(request, fetcher, BASE),
      (error: unknown) => {
        assert.ok(error instanceof V2ApiError);
        assert.equal(
          (error as V2ApiError).status,
          422,
        );
        return true;
      },
    );
  });

  it("recognizes the strategy request-invalid contract only", async () => {
    const fetcher = stubFetch();
    routes.set(URL, {
      status: 422,
      body: { error: "strategy_request_invalid", reason: "x" },
    });
    const failure = await postStrategyCompare(request, fetcher, BASE).then(
      () => null,
      (error: unknown) => error,
    );
    assert.equal(isStrategyRequestInvalid(failure), true);
    assert.equal(isStrategyRequestInvalid(new Error("nope")), false);
  });

  it("forwards abort signals without rewriting them", async () => {
    const fetcher: FetchLike = async (_url: string, init?: RequestInit) => {
      const error = new DOMException("aborted", "AbortError");
      if (init?.signal?.aborted) throw error;
      throw error;
    };
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(
      postStrategyCompare(request, fetcher, BASE, controller.signal),
      (error: unknown) =>
        error instanceof DOMException && error.name === "AbortError",
    );
  });
});
