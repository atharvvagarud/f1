// Counterfactual Explorer pure logic + contract tests (V3.7G).
//
// Covers: request client shape (no seed/count/live fields), deterministic
// demo default, plan construction, N derivation, orientation formatters,
// lifecycle/pairs/interval presentation, failure taxonomy, state copy,
// forbidden-copy audit, and the REAL F response fixtures (captured from
// the frozen F API — never hand-invented).

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CACHE_MISS_COPY,
  COUNTERFACTUAL_FORBIDDEN_COPY,
  DEMO_ANCHOR,
  DEMO_DEFAULT_PLAN,
  DEMO_TARGET,
  INTERVAL_COPY,
  LIFECYCLE_ORDER,
  LIMITATIONS_COPY,
  MAX_INTERVENTIONS,
  METHODOLOGY_COPY,
  NO_INTERVENTION_REFERENCE_COPY,
  PRIMARY_METRIC_ROWS,
  SECONDARY_METRIC_ROWS,
  SUPERSESSION_COPY,
  SUPPORTED_COMPOUNDS,
  buildCompareRequest,
  classifyCounterfactualFailure,
  counterfactualReasonCopy,
  draftRequestKey,
  draftToPlan,
  eligibleNValues,
  formatExpectedFinishDelta,
  formatInterval,
  formatPairs,
  formatPitCount,
  formatPositionGainDelta,
  formatProbabilityDelta,
  gainTone,
  isRivalAllowed,
  lifecycleCounts,
  pitTimingLabel,
  pointOf,
  presetsFor,
  scheduledLap,
  supersededShare,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "./counterfactualMachine.ts";
import {
  getCounterfactualAvailability,
  postCounterfactualCompare,
  type CounterfactualCompareResponse,
  type FetchLike,
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
} from "../../../lib/v2.ts";

const HERE = dirname(fileURLToPath(import.meta.url));

function stubFetch(routes: Map<string, { status: number; body: unknown }>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetcher: FetchLike = async (url, init) => {
    calls.push({ url, init });
    for (const [prefix, response] of routes) {
      if (url.startsWith(prefix)) {
        return {
          ok: response.status >= 200 && response.status < 300,
          status: response.status,
          json: async () => response.body,
        };
      }
    }
    throw new Error(`Unexpected fetch ${url}`);
  };
  return { fetcher, calls };
}

function fixture<T>(name: string): T {
  return JSON.parse(
    readFileSync(join(HERE, "..", "fixtures", `${name}.json`), "utf8"),
  ) as T;
}

// --- client: availability + compare requested, no control fields ---

describe("counterfactual client", () => {
  it("requests availability for the exact anchor", async () => {
    const body = fixture("availability");
    const { fetcher, calls } = stubFetch(
      new Map([["http://api/v2/counterfactuals/availability", { status: 200, body }]]),
    );
    const result = await getCounterfactualAvailability(
      {
        race_id: "2022-r01-R",
        anchor_driver_id: "perez",
        anchor_lap_number: 30,
        anchor_state_time_s: 6745.686,
      },
      fetcher,
      "http://api",
    );
    assert.equal(result.supported, true);
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /race_id=2022-r01-R/);
    assert.match(calls[0].url, /anchor_lap_number=30/);
  });

  it("posts comparisons with no seed, count, or live-mode field", async () => {
    const body = fixture("reference-vs-plan");
    const { fetcher, calls } = stubFetch(
      new Map([["http://api/v2/counterfactuals/compare", { status: 200, body }]]),
    );
    const request = buildCompareRequest(
      { ...DEMO_ANCHOR },
      "REFERENCE_VS_PLAN",
      null,
      { ...DEMO_DEFAULT_PLAN },
      null,
    );
    const raw = JSON.stringify(request);
    for (const forbidden of ["master_seed", "simulation_count", "num_simulations", "seed", "mode", "live", "count"]) {
      assert.doesNotMatch(raw, new RegExp(`"${forbidden}"`), `request leaks ${forbidden}`);
    }
    const result = await postCounterfactualCompare(request, fetcher, "http://api");
    assert.equal(result.supported, true);
    assert.equal(calls.length, 1);
  });
});

// --- deterministic demo default ---

describe("demo default", () => {
  it("is the canonical anchor with the minimal N=1 MEDIUM single stop", () => {
    assert.deepEqual({ ...DEMO_ANCHOR }, {
      race_id: "2022-r01-R",
      anchor_driver_id: "perez",
      anchor_lap_number: 30,
      anchor_state_time_s: 6745.686,
    });
    assert.deepEqual({ ...DEMO_DEFAULT_PLAN }, {
      target_driver_ids: [DEMO_TARGET],
      interventions: [{ target_driver_id: DEMO_TARGET, lap_offset_n: 1, requested_compound: "MEDIUM" }],
    });
  });

  it("request keys are order-invariant across targets and interventions", () => {
    const a = draftRequestKey({
      raceId: "r", anchorDriverId: "a", anchorLapNumber: 1, anchorStateTime: 2,
      form: "REFERENCE_VS_PLAN", base: null,
      alt: { target_driver_ids: ["b", "a"], interventions: [
        { target_driver_id: "b", lap_offset_n: 4, requested_compound: "HARD" },
        { target_driver_id: "a", lap_offset_n: 2, requested_compound: "MEDIUM" },
      ] },
      rival: null,
    });
    const b = draftRequestKey({
      raceId: "r", anchorDriverId: "a", anchorLapNumber: 1, anchorStateTime: 2,
      form: "REFERENCE_VS_PLAN", base: null,
      alt: { target_driver_ids: ["a", "b"], interventions: [
        { target_driver_id: "a", lap_offset_n: 2, requested_compound: "MEDIUM" },
        { target_driver_id: "b", lap_offset_n: 4, requested_compound: "HARD" },
      ] },
      rival: null,
    });
    assert.equal(a, b);
  });
});

// --- plan construction ---

describe("plan construction", () => {
  it("builds reference-vs-plan and plan-vs-plan shapes", () => {
    const alt = draftToPlan(DEMO_DEFAULT_PLAN);
    assert.equal(alt.interventions[0].kind, "PIT_IN_N_LAPS");
    const ref = buildCompareRequest({ ...DEMO_ANCHOR }, "REFERENCE_VS_PLAN", null, DEMO_DEFAULT_PLAN, null);
    assert.equal(ref.comparison_form, "REFERENCE_VS_PLAN");
    assert.equal(ref.base_plan, null);
    const pvp = buildCompareRequest({ ...DEMO_ANCHOR }, "PLAN_VS_PLAN", DEMO_DEFAULT_PLAN, DEMO_DEFAULT_PLAN, null);
    assert.ok(pvp.base_plan !== null);
  });

  it("compounds are exactly SOFT/MEDIUM/HARD/SAMPLED", () => {
    assert.deepEqual(SUPPORTED_COMPOUNDS, ["SOFT", "MEDIUM", "HARD", "SAMPLED"]);
  });

  it("structural cap is 8 interventions", () => {
    assert.equal(MAX_INTERVENTIONS, 8);
  });

  it("multi-stop and multi-driver drafts construct", () => {
    const presets = presetsFor("perez", "russell");
    const keys = presets.map((p) => p.key);
    for (const expected of ["single", "delayed", "multi-stop", "plan-vs-plan", "multi-driver"]) {
      assert.ok(keys.includes(expected), `missing preset ${expected}`);
    }
    const multi = presets.find((p) => p.key === "multi-stop");
    assert.equal(multi?.alt.interventions.length, 2);
    const md = presets.find((p) => p.key === "multi-driver");
    assert.deepEqual([...(md?.alt.target_driver_ids ?? [])].sort(), ["perez", "russell"]);
    for (const preset of presets) {
      assert.ok(!/best|optimal|winning|recommended/i.test(preset.label), preset.label);
    }
  });

  it("rival must differ from targets and be a candidate", () => {
    assert.equal(isRivalAllowed(null, ["perez"], ["russell"]), true);
    assert.equal(isRivalAllowed("russell", ["perez"], ["russell"]), true);
    assert.equal(isRivalAllowed("perez", ["perez"], ["perez", "russell"]), false);
    assert.equal(isRivalAllowed("nobody", ["perez"], ["russell"]), false);
  });
});

// --- N derivation and scheduling display ---

describe("N derivation", () => {
  it("derives eligible N from availability (perez lap 30: 1..26)", () => {
    const avail = fixture<{ drivers: { driver_id: string; eligible_n_min: number | null; eligible_n_max: number | null; eligible: boolean }[] }>("availability");
    const perez = avail.drivers.find((d) => d.driver_id === "perez");
    assert.ok(perez);
    const values = eligibleNValues(perez as never);
    assert.equal(values[0], 1);
    assert.equal(values[values.length - 1], 26);
    assert.equal(values.length, 26);
  });

  it("N=1 schedules at T+1; N>2 at T+N", () => {
    assert.equal(scheduledLap(30, 1), 31);
    assert.equal(scheduledLap(30, 5), 35);
    assert.match(pitTimingLabel(1, 30), /PIT IN 1 LAP.*Scheduled: Lap 31/);
    assert.match(pitTimingLabel(3, 30), /PIT IN 3 LAPS.*Scheduled: Lap 33/);
  });
});

// --- orientation: verbatim, never flipped ---

describe("orientation", () => {
  it("probability deltas render ALT − BASE verbatim", () => {
    assert.equal(formatProbabilityDelta({ metric: "m", point_estimate: 0.05, paired_se: null, ci_low: null, ci_high: null }), "+5.0 pts");
    assert.equal(formatProbabilityDelta({ metric: "m", point_estimate: -0.02, paired_se: null, ci_low: null, ci_high: null }), "−2.0 pts");
    assert.equal(formatProbabilityDelta({ metric: "m", point_estimate: null, paired_se: null, ci_low: null, ci_high: null }), "—");
  });

  it("position gain: +3 gain, 0 neutral, −3 loss", () => {
    const gain = { metric: "delta_position_gain_loss", point_estimate: 3, paired_se: null, ci_low: null, ci_high: null };
    const neutral = { metric: "delta_position_gain_loss", point_estimate: 0, paired_se: null, ci_low: null, ci_high: null };
    const loss = { metric: "delta_position_gain_loss", point_estimate: -3, paired_se: null, ci_low: null, ci_high: null };
    assert.match(formatPositionGainDelta(gain), /^\+.*pos$/);
    assert.equal(gainTone(pointOf(gain)), "gain");
    assert.equal(gainTone(pointOf(neutral)), "neutral");
    assert.equal(gainTone(pointOf(loss)), "loss");
    assert.match(formatPositionGainDelta(loss), /^−.*pos$/);
  });

  it("expected finish renders BASE − ALT verbatim (positive already means ALT improvement)", () => {
    assert.equal(formatExpectedFinishDelta({ metric: "m", point_estimate: 1.5, paired_se: null, ci_low: null, ci_high: null }), "+1.50 pos");
    assert.equal(formatExpectedFinishDelta({ metric: "m", point_estimate: -0.5, paired_se: null, ci_low: null, ci_high: null }), "−0.50 pos");
  });

  it("pit count is descriptive text", () => {
    assert.equal(formatPitCount(2.345), "2.35");
    assert.equal(formatPitCount(null), "—");
  });

  it("primary strip covers WIN/PODIUM/TOP5/EXP/GAIN; secondary covers TOP10/RIVAL/PITS", () => {
    assert.deepEqual(PRIMARY_METRIC_ROWS.map((r) => r.metric), [
      "delta_win_frequency", "delta_podium_frequency", "delta_top5_frequency",
      "delta_expected_finish", "delta_position_gain_loss",
    ]);
    assert.deepEqual(SECONDARY_METRIC_ROWS.map((r) => r.metric), [
      "delta_top10_frequency", "delta_p_ahead_of_rival", "delta_pit_count",
    ]);
    assert.equal(SECONDARY_METRIC_ROWS.find((r) => r.metric === "delta_pit_count")?.improvement, undefined);
  });

  it("real fixture deltas equal recomputed orientations (no flip)", () => {
    const response = fixture<CounterfactualCompareResponse>("reference-vs-plan");
    assert.equal(response.supported, true);
    const base = response.base_aggregate;
    const alt = response.alternative_aggregate;
    assert.ok(base && alt);
    const close = (a: number | null, b: number) => {
      assert.ok(a !== null && Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
    };
    close(response.deltas["delta_expected_finish"].point_estimate, base.expected_finish - alt.expected_finish);
    close(response.deltas["delta_position_gain_loss"].point_estimate, (alt.expected_position_gain ?? 0) - (base.expected_position_gain ?? 0));
    close(response.deltas["delta_win_frequency"].point_estimate, alt.win_frequency - base.win_frequency);
    close(response.deltas["delta_podium_frequency"].point_estimate, alt.podium_frequency - base.podium_frequency);
  });
});

// --- lifecycle, pairs, intervals ---

describe("lifecycle and accounting", () => {
  it("lifecycle vocabulary is complete and never collapsed", () => {
    assert.deepEqual([...LIFECYCLE_ORDER], ["EXECUTED", "INERT", "SUPERSEDED", "CANCELLED", "TERMINAL", "INVALID"]);
  });

  it("real fixture lifecycle sums to requested pairs with visible supersession", () => {
    const response = fixture<CounterfactualCompareResponse>("reference-vs-plan");
    const rows = lifecycleCounts(response);
    assert.ok(rows.length > 0);
    const altRows = rows.filter((r) => r.arm === "alternative");
    const total = altRows.reduce((a, r) => a + r.count, 0);
    assert.equal(total, response.requested_pairs);
    assert.ok(rows.some((r) => r.status === "SUPERSEDED"), "supersession must stay visible");
    assert.ok(supersededShare(response) !== null);
  });

  it("pair accounting formats 5,000 / 5,000", () => {
    assert.equal(formatPairs(5000, 5000), "5,000 / 5,000 complete pairs");
  });

  it("intervals are labelled MC sampling, never confidence", () => {
    assert.match(INTERVAL_COPY, /MC sampling 95% interval/);
    assert.doesNotMatch(INTERVAL_COPY, /confidence/i);
    const withCI = { metric: "m", point_estimate: 0.1, paired_se: 0.01, ci_low: 0.08, ci_high: 0.12 };
    assert.equal(formatInterval(withCI), "[0.080, 0.120]");
    assert.equal(formatInterval({ metric: "m", point_estimate: 0.1, paired_se: null, ci_low: null, ci_high: null }), "—");
  });
});

// --- failure taxonomy ---

describe("failure taxonomy", () => {
  it("distinguishes cache-miss, unknown-race, invalid, server", () => {
    assert.equal(classifyCounterfactualFailure({ status: 404, code: "cache_miss" }).kind, "cache-miss");
    assert.equal(classifyCounterfactualFailure({ status: 404, code: "unknown_race" }).kind, "unknown-race");
    assert.equal(classifyCounterfactualFailure({ status: 422, code: "unknown_state" }).kind, "invalid");
    assert.equal(
      classifyCounterfactualFailure({ status: 422, code: "counterfactual_request_invalid", reason: "invalid_trigger" }).kind,
      "invalid",
    );
    assert.equal(classifyCounterfactualFailure({ status: 503, code: "cache_invalid" }).kind, "server");
    assert.equal(classifyCounterfactualFailure({ status: 500, code: "internal" }).kind, "server");
  });

  it("reason codes map to human copy with codes visible", () => {
    for (const reason of ["INVALID_TRIGGER", "CONFLICTING_INTERVENTIONS", "TARGET_NOT_PRESENT", "RIVAL_NOT_PRESENT", "UNSUPPORTED_INTERVENTION_KIND", "INVALID_PLAN"]) {
      assert.ok(counterfactualReasonCopy(reason).length > 20, reason);
    }
    assert.match(CACHE_MISS_COPY, /not available in the precomputed demo cache/);
    assert.doesNotMatch(CACHE_MISS_COPY, /0|fallback|cheaper/i);
  });

  it("unsupported fixture carries no metrics", () => {
    const response = fixture<CounterfactualCompareResponse>("unsupported");
    assert.equal(response.supported, false);
    assert.equal(response.base_aggregate, null);
    assert.equal(response.alternative_aggregate, null);
    assert.deepEqual(response.deltas, {});
    assert.ok(response.reason_code);
  });

  it("invalid-target fixture is the 422 contract", () => {
    const wrapped = fixture<{ status: number; body: { error: string; reason?: string } }>("invalid-target");
    assert.equal(wrapped.status, 422);
    assert.equal(wrapped.body.error, "counterfactual_request_invalid");
  });
});

// --- real fixture shapes (never hand-invented) ---

describe("contract fixtures", () => {
  it("reference-vs-plan is supported with full scientific content", () => {
    const response = fixture<CounterfactualCompareResponse>("reference-vs-plan");
    assert.equal(response.api_schema, "v3.7f-counterfactual-api-v1");
    assert.equal(response.comparison_form, "REFERENCE_VS_PLAN");
    assert.equal(response.simulation_count, 5000);
    assert.equal(response.master_seed, 20240101);
    assert.equal(response.complete_pairs, 5000);
    assert.ok(response.comparison_identity);
    assert.ok(response.base_aggregate?.finish_position_distribution.length);
    assert.ok(response.alternative_aggregate?.finish_position_distribution.length);
    assert.ok(response.execution_source === "cache" || response.execution_source === "live_engine");
  });

  it("plan-vs-plan identifies BASE plan A and ALT plan B", () => {
    const response = fixture<CounterfactualCompareResponse>("plan-vs-plan");
    assert.equal(response.comparison_form, "PLAN_VS_PLAN");
    assert.ok(response.base_identity);
    assert.ok(response.alternative_identity);
    assert.notEqual(response.base_identity, response.alternative_identity);
  });

  it("multi-stop carries two interventions in one trajectory", () => {
    const response = fixture<CounterfactualCompareResponse>("multi-stop");
    assert.equal(response.supported, true);
    const events = (response.lifecycle_summary["alternative"] && Object.values(response.lifecycle_summary["alternative"]).reduce((a, b) => a + b, 0)) ?? 0;
    assert.equal(events, 2 * (response.requested_pairs ?? 0));
  });

  it("rival fixture exposes P(ahead of rival)", () => {
    const response = fixture<CounterfactualCompareResponse>("rival");
    assert.equal(response.rival_driver_id, "russell");
    assert.ok(response.alternative_aggregate?.p_ahead_of_rival !== null);
    assert.ok(response.deltas["delta_p_ahead_of_rival"]);
  });

  it("multi-driver fixture covers two targets", () => {
    const response = fixture<CounterfactualCompareResponse>("multi-driver");
    assert.deepEqual([...response.target_driver_ids].sort(), ["perez", "russell"]);
  });

  it("availability exposes constraints without futures", () => {
    const avail = fixture<{
      supported: boolean; drivers: unknown[]; eligible_targets: string[];
      supported_compounds: string[]; comparison_forms: string[];
      multi_stop_capable: boolean; multi_driver_capable: boolean;
      rival_candidates: string[]; state_identity: string;
    }>("availability");
    assert.equal(avail.supported, true);
    assert.ok(avail.drivers.length > 0);
    assert.ok(avail.eligible_targets.includes("perez"));
    assert.deepEqual(avail.supported_compounds, ["SOFT", "MEDIUM", "HARD", "SAMPLED"]);
    assert.deepEqual(avail.comparison_forms, ["REFERENCE_VS_PLAN", "PLAN_VS_PLAN"]);
    assert.equal(typeof avail.multi_stop_capable, "boolean");
    assert.ok(avail.rival_candidates.includes("russell"));
    const raw = JSON.stringify(avail);
    assert.doesNotMatch(raw, /"future|"winner|"result"/);
  });
});

// --- copy audit ---

describe("claim audit", () => {
  const sources = [
    "counterfactualMachine.ts",
    "../hooks/useCounterfactuals.ts",
    "../components/CounterfactualView.tsx",
    "../components/CounterfactualPlanBuilder.tsx",
    "../components/CounterfactualResults.tsx",
    "../components/CounterfactualPanels.tsx",
    "../../../lib/v2.ts",
    "../../../components/shell/CommandBar.tsx",
  ];

  it("no recommendation/optimality language in G sources", () => {
    for (const relative of sources) {
      const text = readFileSync(join(HERE, relative), "utf8");
      const lines = text.split("\n");
      lines.forEach((line, index) => {
        // Allow the forbidden-copy list itself and explicit negations.
        if (/FORBIDDEN_COPY|doesNotMatch|assert\.ok\(!|never ranked|no .* language/i.test(line)) return;
        if (/^\s*"[^"]+",?\s*$/.test(line)) return;
        for (const phrase of COUNTERFACTUAL_FORBIDDEN_COPY) {
          if (phrase === "winning" && /winning move/i.test(line)) {
            assert.fail(`${relative}:${index + 1} contains forbidden copy: ${line.trim()}`);
          }
          if (phrase !== "winning" && line.toLowerCase().includes(phrase)) {
            // Explicit prohibition contexts ("never X", "not X", "no X").
            const before = line.toLowerCase().split(phrase)[0];
            const negated = /(never|not|no|without|against|non-|stay bounded|must stay|avoid)\b[^.]{0,60}$/.test(before);
            assert.ok(negated, `${relative}:${index + 1} contains unqualified copy ${JSON.stringify(phrase)}: ${line.trim()}`);
          }
        }
      });
    }
  });

  it("methodology and limitations content exists", () => {
    assert.ok(METHODOLOGY_COPY.length >= 8);
    assert.ok(LIMITATIONS_COPY.length >= 8);
    assert.match(NO_INTERVENTION_REFERENCE_COPY, /without the controlled intervention/);
    assert.match(SUPERSESSION_COPY, /not failure/);
    assert.ok(readFileSync(join(HERE, "..", "fixtures", "reference-vs-plan.json"), "utf8").includes("simulator"));
  });

  it("responsive primitives present in view and builder", () => {
    const view = readFileSync(join(HERE, "..", "components", "CounterfactualView.tsx"), "utf8");
    for (const token of ["sm:", "lg:", "grid-cols-1", "min-w-0", "flex-wrap"]) {
      assert.ok(view.includes(token), `view missing responsive token ${token}`);
    }
    const builder = readFileSync(join(HERE, "..", "components", "CounterfactualPlanBuilder.tsx"), "utf8");
    const panels = readFileSync(join(HERE, "..", "components", "CounterfactualPanels.tsx"), "utf8");
    assert.ok(builder.includes("aria-checked") || builder.includes("radiogroup"));
    assert.ok(panels.includes("aria-expanded"));
    assert.ok(view.includes("role=\"status\"") || view.includes("aria-live"));
  });
});
