// Uncertainty page contract tests (V3.9D). Static source assertions over
// the D surface plus deterministic format checks. No network, no server.
// Run with: node --test features/uncertainty/components/uncertainty-page.test.ts
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..", "..");
const D_FILES = [
  "frontend/app/uncertainty/page.tsx",
  "frontend/features/uncertainty/lib/uncertaintyClient.ts",
  "frontend/features/uncertainty/lib/uncertaintyFormat.ts",
  "frontend/features/uncertainty/hooks/useUncertainty.ts",
  "frontend/features/uncertainty/components/UncertaintyView.tsx",
  "frontend/components/shell/CommandBar.tsx",
];
const src = (p: string): string => readFileSync(join(REPO, p), "utf8");
const ALL = D_FILES.map(src).join("\n");
const VIEW = src("frontend/features/uncertainty/components/UncertaintyView.tsx");
const CLIENT = src("frontend/features/uncertainty/lib/uncertaintyClient.ts");
const HOOK = src("frontend/features/uncertainty/hooks/useUncertainty.ts");

describe("route and navigation", () => {
  it("uncertainty route renders the workspace", () => {
    assert.match(src("frontend/app/uncertainty/page.tsx"), /UncertaintyView/);
  });
  it("navigation links /uncertainty without restructuring", () => {
    assert.match(src("frontend/components/shell/CommandBar.tsx"), /\/uncertainty/);
  });
  it("does not remove the consensus route", () => {
    assert.match(src("frontend/components/shell/CommandBar.tsx"), /\/consensus/);
  });
});

describe("API consumption (frozen V3.9C boundary)", () => {
  it("consumes availability + compare through the API layer", () => {
    assert.match(CLIENT, /\/v2\/uncertainty\/availability/);
    assert.match(CLIENT, /\/v2\/uncertainty\/compare/);
  });
  it("one compare payload serves all drivers; switching is local", () => {
    assert.match(HOOK, /postUncertaintyCompare/);
    assert.match(VIEW, /useState/);
    assert.ok(!/postUncertaintyCompare\(.*driver/i.test(VIEW));
    const selectBlock = VIEW.slice(VIEW.indexOf("onSelect"));
    assert.ok(!/postUncertaintyCompare/.test(selectBlock));
  });
  it("no API call per driver: no looped compare over drivers", () => {
    assert.ok(!/drivers\.map\([^)]*postUncertaintyCompare/.test(ALL));
    assert.ok(!/for\s*\([^)]*driver[^)]*\)[^]*postUncertaintyCompare/.test(ALL));
    assert.ok(!/setInterval|EventSource|WebSocket/.test(HOOK));
  });
  it("no direct results JSON import", () => {
    assert.ok(!/results\/v3\/v3_9[abc]/i.test(ALL));
    assert.ok(!/per_row_records|historical_aggregate|mean gap|median gap/i.test(ALL));
  });
  it("no Python science imports in the frontend", () => {
    assert.ok(!/raceintel\/|ml\/inference|joblib|\.parquet|\.pkl|wilson_interval|average_ranks|mc_sampling_se/i.test(ALL));
  });
  it("no silent demo fallback after failed real request", () => {
    assert.ok(!/fallback.*demo|demo.*fallback|substitut.*demo/i.test(ALL));
    assert.match(VIEW, /Retry/);
  });
});

describe("probability family distinction", () => {
  it("model family label: V3.1B logistic independent binary", () => {
    assert.match(ALL, /V3\.1B [Ll]ogistic/);
    assert.match(ALL, /[Ii]ndependent[- ]binary/);
  });
  it("simulation family label: MC2-E simulation frequency", () => {
    assert.match(ALL, /MC2-E/);
    assert.match(ALL, /[Mm]utually exclusive|[Ss]imulation frequency/);
  });
  it("families shown as different, never interchangeable", () => {
    assert.match(ALL, /Different families|never blended|side by side/i);
  });
});

describe("U1/U2/U3 separation (no collapse)", () => {
  it("three distinct sections exist", () => {
    assert.match(VIEW, /Model × Simulation disagreement/);
    assert.match(VIEW, /Monte Carlo precision/);
    assert.match(VIEW, /Simulator sensitivity/);
  });
  it("no overall/collapsed uncertainty concept", () => {
    assert.ok(!/overall uncertainty|overall confidence|total uncertainty score|uncertainty score/i.test(ALL));
    assert.ok(!/\bTRUST SCORE\b|\btrust score\b|\breliability score\b/i.test(ALL));
    assert.ok(!/confidence score|AI CONFIDENCE|92% CERTAIN|TRUST SCORE/i.test(ALL));
  });
  it("no HIGH/MEDIUM/LOW confidence language", () => {
    assert.ok(!/HIGH confidence|MEDIUM confidence|LOW confidence|high uncertainty|low uncertainty/i.test(ALL));
  });
  it("no fused/blended/averaged probability", () => {
    assert.ok(!/fused_probability|blended_probability|combined_probability|consensus_probability|blendedEstimate|averageProbability/i.test(ALL));
    assert.match(ALL, /no blended probability|never blended/i);
  });
  it("no source winner or preferred source", () => {
    assert.ok(!/winner_source|preferred_source|trusted_source|recommended_probability|trusted estimate|final prediction/i.test(ALL));
    assert.match(ALL, /never.*source winner|no.*source winner/i);
    const banned = [
      "preferred source",
      "recommended probability",
      "trusted source",
      "trusted estimate",
      "Best source",
      "Model is wrong",
      "Simulator is correct",
      "THE MODEL IS WRONG",
      "THE SIMULATOR IS CORRECT",
    ];
    for (const token of banned) {
      assert.ok(!ALL.includes(token), token);
    }
  });
  it("no true-probability claim for the Wilson interval", () => {
    assert.ok(!/TRUE PROBABILITY RANGE|true race probability range|true-probability interval/i.test(ALL));
    assert.match(ALL, /not the true race probability|not total uncertainty/i);
  });
});

describe("U2 precision wording", () => {
  it("panel is Monte Carlo / finite-sampling precision, not bare CI", () => {
    assert.match(ALL, /MONTE CARLO PRECISION|Monte Carlo precision/i);
    assert.match(ALL, /FINITE-SAMPLING|finite-sampling/i);
  });
  it("k/n/p_hat/SE/Wilson all rendered", () => {
    assert.match(VIEW, /Successes k|success_count_k/);
    assert.match(VIEW, /Futures n|valid_futures_n/);
    assert.match(VIEW, /Simulation frequency/);
    assert.match(VIEW, /Finite-sampling SE/);
    assert.match(VIEW, /Wilson 95% lower/);
    assert.match(VIEW, /Wilson 95% upper/);
  });
  it("Wilson visualization is accessible and zero-safe", () => {
    assert.match(VIEW, /role="img"/);
    assert.match(VIEW, /aria-label/);
    assert.match(VIEW, /clamp\(0px/);
  });
});

describe("valid zero rendering", () => {
  it("0.000 renders as evidence with title + inspector context", () => {
    assert.match(VIEW, /0\.000 is valid/);
    assert.ok(!/p_hat === 0 \? "—"|p_hat \? .* : "—"/.test(VIEW));
  });
  it("format contract pins zero behavior", () => {
    const fmt = src("frontend/features/uncertainty/lib/uncertaintyFormat.ts");
    assert.match(fmt, /toFixed\(3\)/);
    assert.ok(!/LOW|MEDIUM|HIGH/.test(fmt));
  });
});

describe("U3 NOT ESTABLISHED", () => {
  it("U3 panel is visible and honest", () => {
    assert.match(VIEW, /SIMULATOR SENSITIVITY|Simulator sensitivity/);
    assert.match(VIEW, /NOT ESTABLISHED|Not established/);
    assert.match(VIEW, /No scientifically defensible parameter perturbation range/);
  });
  it("no numeric U3 bounds, no zero/robust/stable claim", () => {
    assert.ok(!/perturbation range (is|of) [0-9]|range.*±|U3.*0%/i.test(VIEW));
    assert.ok(!/"stable"|"robust"|"LOW"|"NONE"|"0%"|sensitivity.*: *(stable|robust|low|none)/i.test(VIEW));
    assert.match(VIEW, /nothing is claimed about\s+robustness/);
    assert.match(VIEW, /regime_std_s/);
    assert.match(VIEW, /rho/);
    assert.match(VIEW, /provenance insufficient for perturbation bounds/);
  });
  it("U3 is not an error state and not hidden", () => {
    assert.match(VIEW, /limitation of the evidence, not a failure/);
  });
});

describe("status rendering", () => {
  it("all V3.9 statuses have distinct text labels", () => {
    for (const token of [
      "MISSING_SOURCE",
      "UNSUPPORTED_STATE",
      "NOT_APPLICABLE",
      "INSUFFICIENT_SIMULATIONS",
      "PROVENANCE_UNAVAILABLE",
    ]) {
      assert.ok(ALL.includes(token), token);
    }
    assert.match(ALL, /role="status"/);
  });
  it("2025 communicates product-excluded evidence, never zero", () => {
    assert.match(VIEW, /2025 is unsupported for this product evidence/);
    assert.ok(!/zero uncertainty/i.test(VIEW));
  });
  it("loading state has no fake progress", () => {
    assert.match(VIEW, /Loading uncertainty bundle/);
    assert.ok(!/%.*loading|loading.*%|progress/i.test(VIEW));
  });
});

describe("field telemetry neutrality", () => {
  it("values only: spearman, leader match/different, jaccard fraction", () => {
    assert.match(VIEW, /Rank correlation/);
    assert.match(VIEW, /leaderWording/);
    assert.match(ALL, /LEADER MATCH/);
    assert.match(ALL, /LEADER DIFFERENT/);
    assert.match(VIEW, /Top-3 overlap/);
  });
  it("no good/bad agreement, no trustworthy/unreliable", () => {
    assert.ok(!/GOOD AGREEMENT|BAD AGREEMENT|TRUSTWORTHY|UNRELIABLE|good agreement|bad agreement/i.test(ALL));
  });
});

describe("accessibility and responsive markers", () => {
  it("landmarks, headings, scoped table, keyboard selection", () => {
    assert.match(VIEW, /<main/);
    assert.match(VIEW, /<h1/);
    assert.match(VIEW, /scope="col"/);
    assert.match(VIEW, /scope="row"/);
    assert.match(VIEW, /aria-pressed/);
    assert.match(VIEW, /aria-label/);
    assert.match(ALL, /focus-visible/);
  });
  it("direction/status not color-only; abbreviations labelled", () => {
    assert.match(ALL, /simulation higher|model higher/);
    assert.match(VIEW, /<abbr title/);
  });
  it("responsive: stacked grids, internal table scroll, no fixed widths", () => {
    assert.match(VIEW, /overflow-x-auto/);
    assert.match(VIEW, /sm:grid-cols|lg:grid-cols/);
    assert.match(VIEW, /hidden.*md:table-cell/);
    assert.ok(!/min-w-\[390|w-\[1600|width:\s*1600/i.test(VIEW));
  });
  it("native details disclosure for U3 and provenance", () => {
    assert.match(VIEW, /<details/);
  });
  it("reduced motion respected globally", () => {
    const css = readFileSync(join(REPO, "frontend/app/globals.css"), "utf8");
    assert.match(css, /prefers-reduced-motion/);
  });
});

describe("demo state discipline", () => {
  it("deterministic V3.9C-justified anchors only, no 2025 compare", () => {
    assert.match(HOOK, /2022-r03-R/);
    assert.match(HOOK, /2022-r19-R/);
    assert.match(HOOK, /2025-r01-R/);
  });
  it("demo labelled illustrative, never representative", () => {
    assert.match(ALL, /[Ii]llustrative/);
    assert.ok(!/[Rr]epresentative state/.test(ALL));
  });
  it("no historical aggregates as runtime thresholds", () => {
    assert.ok(!/0\.0318|0\.0007|percentile/i.test(ALL));
  });
});
