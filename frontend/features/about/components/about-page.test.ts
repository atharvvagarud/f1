import { strict as assert } from "node:assert";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { validateAboutEvidence } from "../../models/lib/evidence.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..", "..");
const COMPONENTS_DIR = join(REPO, "frontend", "features", "about", "components");
const PAGE = readFileSync(
  join(REPO, "frontend", "app", "about", "page.tsx"),
  "utf8",
);
const ENTRY = readFileSync(
  join(REPO, "frontend", "features", "about", "lib", "aboutEvidence.ts"),
  "utf8",
);
const NAV = readFileSync(
  join(REPO, "frontend", "components", "shell", "CommandBar.tsx"),
  "utf8",
);
const ABOUT = JSON.parse(
  readFileSync(join(REPO, "frontend", "data", "about.v1.json"), "utf8"),
);
const MODELS = JSON.parse(
  readFileSync(join(REPO, "frontend", "data", "models.v1.json"), "utf8"),
);

function componentSources(): Map<string, string> {
  const entries = new Map<string, string>();
  for (const file of readdirSync(COMPONENTS_DIR)) {
    if (file.endsWith(".test.ts")) continue;
    if (file.endsWith(".tsx") || file.endsWith(".ts")) {
      entries.set(
        file,
        readFileSync(join(COMPONENTS_DIR, file), "utf8"),
      );
    }
  }
  return entries;
}

const SOURCES = componentSources();
const ALL_COPY = [...SOURCES.values()].join("\n") + "\n" + PAGE;
// JSX wraps copy across lines; collapse whitespace before literal checks.
const ALL_FLAT = ALL_COPY.replace(/\s+/g, " ");

describe("/about consumes validated P9-1 evidence", () => {
  it("single typed entry point validates about.v1.json", () => {
    assert.match(ENTRY, /validateAboutEvidence/);
    assert.match(ENTRY, /about\.v1\.json/);
    const evidence = validateAboutEvidence(ABOUT);
    assert.equal(evidence.contract_version, "v1");
    assert.equal(evidence.capabilities.length, 8);
  });

  it("page imports entry points and every section, with no fetch", () => {
    assert.match(PAGE, /getAboutEvidence/);
    for (const section of [
      "AboutHeader",
      "SystemOverview",
      "SystemSemantics",
      "ArchitectureMap",
      "CapabilityMap",
      "DataPlatform",
      "TemporalSafety",
      "ReplayIntelligenceFlow",
      "SimulationStrategy",
      "Reproducibility",
      "AboutLimitations",
      "AboutProvenance",
    ]) {
      assert.ok(PAGE.includes(section), `page renders ${section}`);
    }
    assert.ok(!PAGE.includes("fetch("), "no network fetch for evidence");
    assert.ok(!PAGE.includes("use client"), "page is a server component");
    assert.ok(
      !ALL_COPY.includes("about.v1.json"),
      "components never import raw JSON directly",
    );
  });

  it("ABOUT navigation exists alongside existing routes", () => {
    assert.ok(NAV.includes('"/about"'), "ABOUT route in nav");
    assert.ok(NAV.includes("About"), "ABOUT label in nav");
    for (const route of ['"/"', '"/replay"', '"/simulator"', '"/strategy"', '"/models"']) {
      assert.ok(NAV.includes(route), `existing route ${route} preserved`);
    }
  });

  it("FACT/PREDICTION/SIMULATION/STRATEGY are distinct", () => {
    for (const id of ["FACT", "PREDICTION", "SIMULATION", "STRATEGY"]) {
      assert.ok(ALL_COPY.includes(id), `${id} visible`);
    }
    assert.ok(ALL_COPY.includes("system_semantics"), "renders from contract");
    assert.ok(
      ALL_COPY.includes("not_to_confuse_with"),
      "renders not-to-confuse-with lines",
    );
    const ids = ABOUT.system_semantics.map((s: { id: string }) => s.id);
    assert.deepEqual(ids, ["FACT", "PREDICTION", "SIMULATION", "STRATEGY"]);
  });

  it("prediction is explicitly independent-binary", () => {
    assert.ok(ALL_COPY.includes("INDEPENDENT_BINARY"));
    assert.ok(
      ALL_FLAT.includes("not expected to sum to 1"),
      "non-share meaning is visible",
    );
    assert.ok(ALL_COPY.includes("probability_semantics"));
  });

  it("simulation semantics are distinct from prediction", () => {
    assert.ok(ALL_COPY.includes("MUTUALLY_EXCLUSIVE_FREQUENCY"));
    assert.ok(
      ALL_FLAT.includes("different probability semantics"),
      "difference stated explicitly",
    );
    assert.ok(
      ALL_FLAT.includes("not fed into the Monte Carlo"),
      "no prediction-into-simulation implication",
    );
  });

  it("strategy is paired/CRN comparison without endorsement", () => {
    assert.ok(/common random numbers/i.test(ALL_COPY), "CRN visible");
    assert.ok(ALL_FLAT.includes("Paired"), "paired wording visible");
    assert.ok(ALL_COPY.includes("IMPROVEMENT"), "outcome vocabulary visible");
    assert.ok(ALL_COPY.includes("INCONCLUSIVE"), "outcome vocabulary visible");
    assert.ok(ALL_COPY.includes("UNAVAILABLE"), "outcome vocabulary visible");
  });

  it("8 implemented capabilities render with scope", () => {
    assert.equal(ABOUT.capabilities.length, 8);
    assert.ok(ALL_COPY.includes("capabilities"), "renders from contract");
    assert.ok(ALL_COPY.includes("capability.name"), "renders names");
    assert.deepEqual(
      ABOUT.capabilities.map((c: { name: string }) => c.name),
      [
        "Historical Data Platform",
        "Temporal Feature Engine",
        "Model Lab",
        "Race State plus Prediction",
        "Historical Replay",
        "Monte Carlo Engine",
        "Strategy Engine",
        "Replay Intelligence",
      ],
    );
    assert.ok(ALL_COPY.includes("capability.does"), "renders does");
    assert.ok(ALL_COPY.includes("capability.does_not"), "renders does_not");
    assert.deepEqual(
      ABOUT.capabilities.map((c: { phase: number }) => c.phase),
      [1, 2, 3, 4, 5, 6, 7, 8],
    );
  });

  it("dataset statistics are exact", () => {
    const tierA = ABOUT.dataset_statistics.tier_a;
    assert.equal(tierA.terminal_sessions, 173);
    assert.equal(tierA.complete, 171);
    assert.equal(tierA.partial, 2);
    assert.equal(tierA.driver_laps, 189420);
    assert.equal(tierA.results, 3458);
    assert.equal(tierA.pit_stops, 6336);
    assert.equal(tierA.stints, 9324);
    assert.equal(tierA.weather_rows, 25779);
    assert.equal(tierA.race_control_rows, 14992);
    const tierB = ABOUT.dataset_statistics.tier_b;
    assert.equal(tierB.seasons_count, 76);
    assert.equal(tierB.races, 1149);
    assert.equal(tierB.results, 25784);
    assert.equal(ABOUT.dataset_statistics.phase2.states, 189420);
    assert.equal(ABOUT.dataset_statistics.phase2.predictive_features, 84);
    assert.equal(ABOUT.dataset_statistics.replay.served_races, 149);
    assert.equal(ABOUT.dataset_statistics.replay.checkpoints, 9644);
    assert.equal(ABOUT.dataset_statistics.replay.observable_predictions, 189610);
    // Counts render at runtime via toLocaleString; source carries the
    // accessors plus human-readable labels, JSON carries exact values.
    assert.ok(ALL_COPY.includes("toLocaleString"), "formats counts");
    for (const label of [
      "Terminal sessions",
      "Driver laps",
      "Pit stops",
      "Weather rows",
      "Race-control rows",
      "Served races",
      "Checkpoints",
      "Observable predictions",
    ]) {
      assert.ok(ALL_FLAT.includes(label), `statistic labeled: ${label}`);
    }
  });

  it("2025 boundary is explicit: data vs serving vs holdout", () => {
    assert.ok(ALL_FLAT.includes("2018-2025"), "data coverage visible");
    assert.ok(ALL_FLAT.includes("2018-2024"), "served boundary visible");
    assert.ok(/frozen holdout/i.test(ALL_COPY), "holdout wording visible");
    assert.ok(/not served/i.test(ALL_COPY), "unserved wording visible");
    assert.ok(
      ALL_COPY.includes("serving_scope_note"),
      "serving scope note rendered",
    );
  });

  it("bounded leakage statement is exact", () => {
    assert.ok(
      ALL_COPY.includes("safeguards.statement") ||
        ALL_COPY.includes(
          "No temporal leakage was detected under the implemented adversarial test suite.",
        ),
      "bounded statement rendered from contract",
    );
    assert.equal(
      MODELS.temporal_safeguards.statement,
      "No temporal leakage was detected under the implemented adversarial test suite.",
    );
    assert.ok(ALL_COPY.includes("safeguards.items"), "safeguard items render");
  });

  it("architecture matches implementation; absent stack stays absent", () => {
    // Rows render at runtime from the contract arrays; source carries the
    // accessors, JSON carries the exact implemented / not-used split.
    assert.ok(
      ALL_COPY.includes("architecture.implemented"),
      "renders implemented stack",
    );
    assert.deepEqual(ABOUT.architecture.implemented, [
      "Next.js frontend",
      "FastAPI backend",
      "Canonical Parquet data",
      "Phase-2 model matrix",
      "Frozen sklearn serving artifact",
      "Offline replay cache",
      "Monte Carlo engine",
      "Strategy engine",
    ]);
    assert.ok(
      ALL_FLAT.includes("Intentionally not part of current architecture"),
      "not-used section headed explicitly",
    );
    assert.ok(
      ALL_COPY.includes("architecture.not_used"),
      "renders not-used block",
    );
    assert.deepEqual(ABOUT.architecture.not_used, [
      "Postgres",
      "Timescale",
      "Redis",
      "WebSockets",
      "Celery/RQ",
      "MLflow",
      "Kubernetes",
      "Kafka",
      "live F1 feeds",
    ]);
  });

  it("reproducibility and Phase 1-8 freezes are visible", () => {
    assert.ok(ALL_COPY.includes("freeze_tags"), "freeze tags render");
    // Tags render at runtime from the contract array; source carries the
    // accessor plus the static phase labels, JSON carries exact tags.
    assert.ok(ALL_FLAT.includes("P8 Replay intelligence"), "timeline labeled");
    assert.deepEqual(ABOUT.reproducibility.freeze_tags, [
      "v2-data-platform-phase1",
      "v2-temporal-feature-engine-phase2",
      "v2-model-lab-phase3",
      "v2-race-state-prediction-phase4",
      "v2-historical-replay-phase5",
      "v2-monte-carlo-phase6",
      "v2-strategy-engine-phase7",
      "v2-replay-intelligence-phase8",
    ]);
    assert.ok(ALL_COPY.includes("deterministic_seeds"), "seeds render");
    assert.ok(ALL_COPY.includes("make_targets"), "make targets render");
    assert.ok(ALL_COPY.includes("manifests"), "manifests render");
    assert.ok(ALL_COPY.includes("artifact_hashes"), "hashes render");
    assert.ok(
      ALL_COPY.includes("repro.note") ||
        ALL_COPY.includes("reproducibility.note"),
      "no-one-command note rendered",
    );
    assert.equal(
      ABOUT.reproducibility.note,
      "Per-phase validation reports document reproduction; no single-command full reproduction is claimed.",
    );
  });

  it("limitations and provenance are visible", () => {
    assert.equal(ABOUT.limitations.length, 9);
    assert.ok(
      ALL_FLAT.includes("What the system does not claim"),
      "limitations headed prominently",
    );
    assert.ok(ALL_COPY.includes("limitation.text"), "renders limitation text");
    assert.ok(ALL_COPY.includes("phase8_freeze_tag"), "renders freeze tag");
    assert.equal(
      ABOUT.provenance.phase8_freeze_tag,
      "v2-replay-intelligence-phase8",
    );
  });

  it("no scientific recomputation helpers and no backend fetch", () => {
    for (const [file, source] of SOURCES) {
      assert.ok(!source.includes(".sort("), `${file}: no sorting`);
      assert.ok(!source.includes("fetch("), `${file}: no fetch`);
      assert.ok(!source.includes("/api"), `${file}: no backend route`);
      assert.ok(
        !source.includes("predict_proba"),
        `${file}: no model execution`,
      );
      assert.ok(!source.includes("read_parquet"), `${file}: no parquet reads`);
      assert.ok(!source.includes("joblib"), `${file}: no artifact loading`);
    }
    assert.ok(!/normalize/i.test(ALL_COPY), "no probability normalization");
  });

  it("language red-team rejects unsupported claims", () => {
    const lower = ALL_COPY.toLowerCase();
    for (const phrase of [
      "real-time f1",
      "live race engineer",
      "ai race engineer",
      "production f1",
      "professional f1 system",
      "optimal strategy",
      "best strategy",
      "recommended strategy",
      "recommendation",
      "guaranteed improvement",
      "perfect simulation",
      "leakage free",
      "leakage-free",
      "zero leakage",
      "reason driver won",
      "production scale",
      "production-scale",
      "ai-powered",
    ]) {
      assert.ok(!lower.includes(phrase), `banned phrase present: ${phrase}`);
    }
    // "live F1 feeds" is a contract not_used item rendered at runtime
    // from architecture.not_used under the explicit absent-heading: the
    // page must contain no other live wording.
    assert.ok(
      ALL_COPY.includes("architecture.not_used"),
      "not-used block rendered from contract",
    );
    assert.ok(!lower.includes("live"), "no live wording in page copy");
    assert.ok(!/caused/i.test(ALL_COPY), "no causal verb");
  });
});
