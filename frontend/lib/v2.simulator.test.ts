import { strict as assert } from "node:assert";
import { beforeEach, describe, it } from "node:test";
import {
  V2ApiError,
  isSimulationUnsupported,
  postRaceSimulation,
  type FetchLike,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./v2.ts";

// V2 simulator client (lib/v2.ts): POST payload/URL, response pass-through,
// and the stable 422 simulation_unsupported contract. fetch is stubbed.

const BASE = "http://127.0.0.1:8000";
const URL = `${BASE}/v2/simulations/race`;

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
  simulation_count: 1000,
};

const body = {
  race_id: "2022-r01-R",
  anchor_driver_id: "perez",
  anchor_lap_number: 30,
  anchor_state_time_s: 6745.686,
  probability_semantics: "MONTE_CARLO_FREQUENCY",
  requested_simulation_count: 1000,
  valid_simulations: 1000,
  invalid_simulations: 0,
  master_seed: 20240101,
  drivers: [
    { driver_id: "a", win_probability: 0.61, podium_probability: 0.9 },
    { driver_id: "b", win_probability: 0.39, podium_probability: 0.8 },
  ],
};

describe("postRaceSimulation", () => {
  let fetcher: FetchLike;
  beforeEach(() => {
    fetcher = stubFetch();
  });

  it("POSTs the exact-anchor payload to /v2/simulations/race", async () => {
    routes.set(URL, { status: 200, body });
    const data = await postRaceSimulation(request, fetcher);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, URL);
    assert.equal(calls[0].init?.method, "POST");
    assert.equal(
      (calls[0].init?.headers as Record<string, string>)["Content-Type"],
      "application/json",
    );
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), request);
    assert.equal(data.probability_semantics, "MONTE_CARLO_FREQUENCY");
  });

  it("passes probabilities through verbatim (never normalized client-side)", async () => {
    routes.set(URL, { status: 200, body });
    const data = await postRaceSimulation(request, fetcher);
    assert.equal(data.drivers[0].win_probability, 0.61);
    assert.equal(data.drivers[1].win_probability, 0.39);
    assert.equal(
      data.drivers.reduce((acc, d) => acc + d.win_probability, 0),
      1.0,
    );
  });

  it("parses 422 simulation_unsupported with its stable reason", async () => {
    routes.set(URL, {
      status: 422,
      body: {
        error: "simulation_unsupported",
        reason: "non_contemporaneous_roster_member",
        detail: "roster members ...",
      },
    });
    await assert.rejects(postRaceSimulation(request, fetcher), (error: unknown) => {
      assert.ok(error instanceof V2ApiError);
      assert.equal(error.status, 422);
      assert.equal(error.code, "simulation_unsupported");
      assert.equal(error.reason, "non_contemporaneous_roster_member");
      assert.equal(isSimulationUnsupported(error), true);
      return true;
    });
  });

  it("a 404 unknown_race is not an unsupported-state contract", async () => {
    routes.set(URL, {
      status: 404,
      body: { error: "unknown_race", detail: "no served race" },
    });
    await assert.rejects(postRaceSimulation(request, fetcher), (error: unknown) => {
      assert.ok(error instanceof V2ApiError);
      assert.equal(isSimulationUnsupported(error), false);
      return true;
    });
  });
});
