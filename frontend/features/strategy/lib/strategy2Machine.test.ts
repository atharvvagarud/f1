import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CACHE_MISS_COPY,
  DOWNSIDE_COPY,
  INTERVAL_COPY,
  LEADER_COPY,
  REFERENCE_COPY,
  STRATEGY2_FORBIDDEN_COPY,
  STRATEGY2_LEADER_LABELS,
  STRATEGY2_TRADE_OFF_ROWS,
  aggregateFor,
  classifyStrategy2Failure,
  deltaFor,
  formatDownside,
  formatPairs,
  groupAvailabilityByRace,
  leadsFor,
  strategy2ReasonCopy,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./strategy2Machine.ts";
import {
  getStrategyV3Availability,
  isStrategyV3CacheMiss,
  isStrategyV3RequestInvalid,
  postStrategyV3Compare,
  type FetchLike,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "../../../lib/v2.ts";

// Strategy 2.0 pure logic + client: frozen trade-off vector, orientation,
// error taxonomy, catalogue grouping, cached-mode default, copy guards.

const HERE = dirname(fileURLToPath(import.meta.url));

function stubFetch(routes: Map<string, { status: number; body: unknown }>) {
  const calls: { url: string; init?: RequestInit }[] = [];
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
  return { fetcher, calls };
}

describe("strategy2 trade-off vector", () => {
  it("covers all six frozen metrics in backend order", () => {
    assert.deepEqual(
      STRATEGY2_TRADE_OFF_ROWS.map((r) => r.metric),
      [
        "delta_win_frequency",
        "delta_podium_frequency",
        "delta_top5_frequency",
        "delta_top10_frequency",
        "delta_expected_finish",
        "delta_downside_probability",
      ],
    );
  });

  it("delta lookup is exact by metric", () => {
    const alt = {
      deltas: [
        { metric: "delta_win_frequency", point_estimate: 0.013 },
        { metric: "delta_expected_finish", point_estimate: 0.7 },
      ],
    };
    assert.equal(
      deltaFor(alt as never, "delta_win_frequency")?.point_estimate,
      0.013,
    );
    assert.equal(deltaFor(alt as never, "nope"), null);
  });

  it("reference and alternative aggregates read the matching arm", () => {
    const alt = {
      reference_aggregate: {
        win_frequency: 0.081,
        podium_frequency: 0.247,
        top5_frequency: 0.613,
        top10_frequency: 0.941,
        expected_finish: 5.8,
      },
      alternative_aggregate: {
        win_frequency: 0.094,
        podium_frequency: 0.302,
        top5_frequency: 0.688,
        top10_frequency: 0.95,
        expected_finish: 5.1,
      },
      deltas: [],
    };
    assert.equal(aggregateFor(alt as never, "delta_win_frequency", "reference"), 0.081);
    assert.equal(aggregateFor(alt as never, "delta_expected_finish", "alternative"), 5.1);
    assert.equal(
      aggregateFor({ ...alt, reference_aggregate: null } as never, "delta_win_frequency", "reference"),
      null,
    );
  });

  it("downside aggregate is the backend downside point estimate", () => {
    const alt = {
      reference_aggregate: null,
      alternative_aggregate: null,
      deltas: [{ metric: "delta_downside_probability", point_estimate: 0.314 }],
    };
    assert.equal(
      aggregateFor(alt as never, "delta_downside_probability", "alternative"),
      0.314,
    );
  });
});

describe("strategy2 leaders", () => {
  it("maps leader keys without inventing a global winner", () => {
    assert.equal(Object.keys(STRATEGY2_LEADER_LABELS).length, 5);
    assert.ok(!("leader_for_downside_probability" in STRATEGY2_LEADER_LABELS));
    const leaders = {
      leader_for_win_frequency: "STAY_OUT:SAMPLED",
      leader_for_podium_frequency: "PIT_NOW:MEDIUM",
      leader_for_top5_frequency: "PIT_NOW:MEDIUM",
      leader_for_top10_frequency: null,
      leader_for_expected_finish: "STAY_OUT:SAMPLED",
    };
    assert.deepEqual(leadsFor("PIT_NOW:MEDIUM", leaders), [
      "leader_for_podium_frequency",
      "leader_for_top5_frequency",
    ]);
    assert.deepEqual(leadsFor("PIT_NOW:SOFT", leaders), []);
  });

  it("leader copy denies recommendation explicitly", () => {
    assert.ok(LEADER_COPY.includes("not a"));
    assert.ok(LEADER_COPY.includes("recommendation"));
    assert.ok(LEADER_COPY.includes("no overall winner") || LEADER_COPY.includes("disagree"));
  });
});

describe("strategy2 copy semantics", () => {
  it("downside copy denies the wrong reading", () => {
    assert.ok(DOWNSIDE_COPY.includes("worse"));
    assert.ok(DOWNSIDE_COPY.includes("Not the probability"));
  });

  it("interval copy denies certainty readings", () => {
    assert.ok(INTERVAL_COPY.includes("Sampling uncertainty"));
    assert.ok(INTERVAL_COPY.includes("Not"));
  });

  it("reference copy never calls it a team strategy", () => {
    assert.ok(REFERENCE_COPY.includes("without forcing"));
    for (const word of ["current strategy", "team strategy", "stay out", "historical strategy"]) {
      assert.ok(!REFERENCE_COPY.toLowerCase().includes(word), word);
    }
  });

  it("reason codes map to human copy without dropping the code", () => {
    assert.ok(strategy2ReasonCopy("target_driver_not_in_roster").includes("roster"));
    assert.ok(strategy2ReasonCopy("NO_VALID_PAIRS").includes("paired"));
    assert.ok(strategy2ReasonCopy("wet_track_conditions").includes("dry-only"));
    assert.ok(strategy2ReasonCopy("STALE_ROSTER_OBSERVATION").includes("field"));
    assert.ok(strategy2ReasonCopy(null).length > 10);
  });

  it("pair counts render requested and complete", () => {
    assert.equal(formatPairs(4982, 5000), "4,982 / 5,000 complete pairs");
  });

  it("downside formats as a percentage", () => {
    assert.equal(formatDownside(0.314), "31.4%");
    assert.equal(formatDownside(null), "—");
  });
});

describe("strategy2 failure taxonomy", () => {
  it("distinguishes cache miss from failure", () => {
    assert.deepEqual(classifyStrategy2Failure({ status: 404, code: "cache_miss" }), {
      kind: "cache-miss",
    });
    assert.ok(CACHE_MISS_COPY.includes("precomputed"));
  });

  it("2025/unknown race is unavailable, not a crash", () => {
    const failure = classifyStrategy2Failure({ status: 404, code: "unknown_race" });
    assert.equal(failure.kind, "unavailable");
  });

  it("invalid requests stay invalid", () => {
    assert.equal(
      classifyStrategy2Failure({ status: 422, code: "strategy_v3_request_invalid", reason: "invalid_action" }).kind,
      "invalid",
    );
    assert.equal(
      classifyStrategy2Failure({ status: 422, code: "unknown_state" }).kind,
      "invalid",
    );
  });

  it("server problems stay server problems", () => {
    assert.equal(classifyStrategy2Failure({ status: 500, code: "internal" }).kind, "server");
    assert.equal(
      classifyStrategy2Failure({ status: 503, code: "live_engine_disabled" }).kind,
      "server",
    );
  });
});

describe("strategy2 availability catalogue", () => {
  it("groups deterministically by race", () => {
    const entries = [
      { race_id: "2022-r01-R", anchor_lap_number: 30, anchor_state_time_s: 6745.686, target_driver_id: "perez" },
      { race_id: "2018-r11-R", anchor_lap_number: 44, anchor_state_time_s: 4004.408, target_driver_id: "alonso" },
      { race_id: "2022-r01-R", anchor_lap_number: 10, anchor_state_time_s: 1000.0, target_driver_id: "alonso" },
    ];
    const groups = groupAvailabilityByRace(entries as never);
    assert.equal(groups.length, 2);
    assert.equal(groups[0].race_id, "2018-r11-R");
    assert.equal(groups[1].entries[0].anchor_lap_number, 10);
    assert.equal(groups[1].entries[1].anchor_lap_number, 30);
  });
});

describe("strategy2 API client", () => {
  const BASE = "http://127.0.0.1:8000";

  it("posts compare-v3 with cached mode and no simulation count", async () => {
    const routes = new Map([
      [`${BASE}/v2/strategies/compare-v3`, { status: 200, body: { supported: true } }],
    ]);
    const { fetcher, calls } = stubFetch(routes);
    const response = await postStrategyV3Compare(
      {
        race_id: "2022-r01-R",
        anchor_driver_id: "perez",
        anchor_lap_number: 30,
        anchor_state_time_s: 6745.686,
        target_driver_id: "perez",
        alternatives: [{ action: "STAY_OUT" }],
        mode: "cached",
      },
      fetcher,
      BASE,
    );
    assert.deepEqual(response, { supported: true });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, `${BASE}/v2/strategies/compare-v3`);
    const sent = JSON.parse((calls[0].init?.body ?? "{}") as string);
    assert.equal(sent.mode, "cached");
    assert.ok(!("simulation_count" in sent), "no arbitrary count is ever sent");
  });

  it("fetches the availability catalogue", async () => {
    const routes = new Map([
      [
        `${BASE}/v2/strategies/v3/availability`,
        { status: 200, body: { entry_count: 0, entries: [] } },
      ],
    ]);
    const { fetcher, calls } = stubFetch(routes);
    const catalogue = await getStrategyV3Availability(fetcher, BASE);
    assert.deepEqual(catalogue.entries, []);
    assert.equal(calls[0].url, `${BASE}/v2/strategies/v3/availability`);
  });

  it("recognizes request-invalid and cache-miss contracts", async () => {
    const routes = new Map([
      [
        `${BASE}/v2/strategies/compare-v3`,
        { status: 422, body: { error: "strategy_v3_request_invalid", reason: "invalid_action" } },
      ],
    ]);
    const { fetcher } = stubFetch(routes);
    await assert.rejects(
      postStrategyV3Compare(
        {
          race_id: "x",
          anchor_driver_id: "y",
          anchor_lap_number: 1,
          anchor_state_time_s: 1.0,
          target_driver_id: "z",
          mode: "cached",
        },
        fetcher,
        BASE,
      ),
      (error: unknown) => isStrategyV3RequestInvalid(error),
    );
    assert.ok(
      isStrategyV3CacheMiss(
        Object.assign(new Error("x"), { status: 404, code: "cache_miss" }) as never,
      ) === false,
      "plain errors are not cache misses",
    );
  });
});

describe("strategy2 copy guard", () => {
  const SOURCES = [
    "strategy2Machine.ts",
    "../components/Strategy2View.tsx",
    "../components/Strategy2Results.tsx",
    "../hooks/useStrategy2.ts",
    "../../../app/strategy/page.tsx",
  ];

  it("contains no recommendation or certainty language", () => {
    const missing = SOURCES.filter((name) => {
      try {
        readFileSync(join(HERE, name), "utf8");
        return false;
      } catch {
        return true;
      }
    });
    assert.deepEqual(missing, [], "all Strategy 2.0 sources must exist");
    for (const name of SOURCES) {
      const raw = readFileSync(join(HERE, name), "utf8").toLowerCase();
      // The forbidden-phrase list definition itself is not product copy.
      const text = raw.replace(
        /export const strategy2_forbidden_copy = \[[\s\S]*?\];/,
        "",
      );
      for (const forbidden of STRATEGY2_FORBIDDEN_COPY) {
        const occurrences = text.split(forbidden).length - 1;
        const denied =
          text.includes(`not a ${forbidden}`) ||
          text.includes(`never ${forbidden}`) ||
          text.includes(`no ${forbidden}`) ||
          text.includes(`not the ${forbidden}`);
        assert.ok(
          occurrences === 0 || denied,
          `${name} contains forbidden copy: ${forbidden}`,
        );
      }
    }
  });
});
