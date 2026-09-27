import { strict as assert } from "node:assert";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { validateModelsEvidence } from "../lib/evidence.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..", "..");
const COMPONENTS_DIR = join(REPO, "frontend", "features", "models", "components");
const PAGE = readFileSync(
  join(REPO, "frontend", "app", "models", "page.tsx"),
  "utf8",
);
const ENTRY = readFileSync(
  join(REPO, "frontend", "features", "models", "lib", "modelsEvidence.ts"),
  "utf8",
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

function metric(id: string) {
  const found = MODELS.holdout_evidence.metrics.find(
    (entry: { id: string }) => entry.id === id,
  );
  assert.ok(found, `metric ${id} present`);
  return found;
}

describe("/models consumes validated P9-1 evidence", () => {
  it("single typed entry point validates models.v1.json", () => {
    assert.match(ENTRY, /validateModelsEvidence/);
    assert.match(ENTRY, /models\.v1\.json/);
    const evidence = validateModelsEvidence(MODELS);
    assert.equal(evidence.model_spec.estimator, "LogisticRegression");
  });

  it("page imports the entry point and every section, with no fetch", () => {
    assert.match(PAGE, /getModelsEvidence/);
    for (const section of [
      "ModelHeader",
      "ProductionModel",
      "HoldoutPerformance",
      "TemporalEvaluation",
      "DevelopmentComparison",
      "CalibrationEvidence",
      "FeatureSystem",
      "GlobalEvidence",
      "ScientificSafeguards",
      "ModelLimitations",
      "EvidenceProvenance",
    ]) {
      assert.ok(PAGE.includes(section), `page renders ${section}`);
    }
    assert.ok(!PAGE.includes("fetch("), "no network fetch for evidence");
    assert.ok(!PAGE.includes("use client"), "page is a server component");
    assert.ok(
      !ALL_COPY.includes("models.v1.json"),
      "components never import raw JSON directly",
    );
  });

  it("production model identity renders", () => {
    assert.ok(ALL_COPY.includes("model_spec"), "reads model_spec");
    assert.ok(ALL_COPY.includes("spec.estimator"), "renders estimator");
    assert.ok(
      ALL_COPY.includes("probability_semantics"),
      "renders semantics field",
    );
    assert.equal(MODELS.model_spec.estimator, "LogisticRegression");
    assert.equal(
      MODELS.model_spec.probability_semantics,
      "INDEPENDENT_BINARY",
    );
    assert.ok(
      ALL_FLAT.includes("estimated independently"),
      "independent-binary meaning is visible",
    );
    assert.ok(ALL_FLAT.includes("not expected to sum to 1"));
  });

  it("holdout says frozen one-shot with exact population", () => {
    assert.ok(/one-shot/i.test(ALL_COPY), "one-shot wording visible");
    assert.ok(/not development/i.test(ALL_COPY));
    const holdout = MODELS.holdout_evidence;
    assert.equal(holdout.population.races, 24);
    assert.equal(holdout.population.eligible_states, 26692);
    assert.ok(ALL_COPY.includes("eligible_states"));
    assert.ok(ALL_COPY.includes("races} races"));
    assert.equal(metric("race_macro_log_loss").value, 0.06803537409512433);
    assert.equal(metric("race_macro_log_loss").role, "PRIMARY");
  });

  it("no composite score and no generic accuracy headline", () => {
    assert.ok(!/composite/i.test(ALL_COPY));
    assert.ok(!/>accuracy</i.test(ALL_COPY));
    assert.ok(ALL_COPY.includes("metric.display_name"), "names from evidence");
    const names = MODELS.holdout_evidence.metrics.map(
      (m: { display_name: string }) => m.display_name,
    );
    assert.ok(names.includes("Synchronized top-1"));
    assert.ok(names.includes("Synchronized top-3"));
  });

  it("2025 is separated from development", () => {
    assert.ok(/isolated from development/i.test(ALL_COPY));
    assert.ok(!("holdout" in MODELS.development_evidence));
  });

  it("temporal folds render exactly", () => {
    assert.ok(
      ALL_COPY.includes("development_folds"),
      "renders development folds",
    );
    const folds = MODELS.temporal_evaluation.development_folds;
    assert.deepEqual(
      folds.map((f: { train: string; validate: number }) => [
        f.train,
        f.validate,
      ]),
      [
        ["2018-2021", 2022],
        ["2018-2022", 2023],
        ["2018-2023", 2024],
      ],
    );
    assert.ok(ALL_COPY.includes("FINAL_FIT") || ALL_COPY.includes("Final fit"));
    assert.ok(ALL_COPY.includes("Holdout"));
  });

  it("development candidates use dev evidence only, folds visible, no ranking", () => {
    assert.equal(MODELS.development_evidence.candidates.length, 9);
    assert.ok(ALL_COPY.includes("Development-only"));
    assert.ok(ALL_COPY.includes("Frozen serving choice"));
    for (const header of ["RANK", "BEST", "WINNER", "SCORE"]) {
      assert.ok(
        !new RegExp(`>${header}<`).test(ALL_COPY),
        `no ${header} leaderboard column`,
      );
    }
  });

  it("calibration is development-only with RAW frozen", () => {
    assert.ok(/development-only/i.test(ALL_COPY));
    assert.ok(ALL_COPY.includes("RAW — frozen"));
    assert.equal(MODELS.calibration_evidence.selected_method, "RAW");
  });

  it("84/106 and 8 families with exact counts", () => {
    assert.ok(ALL_FLAT.includes("84 canonical"));
    assert.ok(ALL_FLAT.includes("106 transformed"));
    assert.ok(ALL_COPY.includes("feature_names_by_family"));
    const families = MODELS.feature_system.families;
    assert.equal(families.length, 8);
    assert.deepEqual(
      families.map((f: { family: string }) => f.family),
      [
        "STATE",
        "PACE",
        "GAPS",
        "FIELD_CONTEXT",
        "RATES_MOMENTUM",
        "ENVIRONMENT_HISTORY",
        "PRE_RACE_PRIORS",
        "INTERACTIONS",
      ],
    );
    assert.equal(
      families.reduce((sum: number, f: { count: number }) => sum + f.count, 0),
      84,
    );
  });

  it("coefficient evidence is LOG_ODDS with accessible direction", () => {
    assert.ok(ALL_COPY.includes("LOG_ODDS"));
    assert.ok(ALL_COPY.includes("Positive log-odds"));
    assert.ok(ALL_COPY.includes("Negative log-odds"));
  });

  it("permutation panel is visibly in-sample and not temporally OOS", () => {
    assert.ok(ALL_COPY.includes("PRE_2025_FINAL_FIT_IN_SAMPLE"));
    assert.ok(
      ALL_COPY.includes("perm.evidence_class_note"),
      "renders the contract in-sample note",
    );
    assert.match(
      MODELS.permutation_evidence.evidence_class_note,
      /NOT temporally out-of-sample/,
      "contract carries the not-OOS wording",
    );
    assert.ok(!/feature importance/i.test(ALL_COPY));
    assert.equal(
      MODELS.permutation_evidence.evidence_class,
      "PRE_2025_FINAL_FIT_IN_SAMPLE",
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
    assert.equal(MODELS.temporal_safeguards.items.length, 7);
  });

  it("limitations and provenance are visible", () => {
    assert.ok(ALL_COPY.includes("What this evidence does not support"));
    assert.ok(ALL_COPY.includes("Evidence / provenance"));
    assert.ok(ALL_COPY.includes("phase8_freeze_tag"), "renders freeze tag");
    assert.equal(
      MODELS.provenance.phase8_freeze_tag,
      "v2-replay-intelligence-phase8",
    );
  });

  it("no scientific recomputation helpers and no backend fetch", () => {
    for (const [file, source] of SOURCES) {
      if (file === "format.ts") continue;
      assert.ok(!source.includes(".sort("), `${file}: no sorting`);
      assert.ok(!source.includes("fetch("), `${file}: no fetch`);
      assert.ok(!source.includes("/api"), `${file}: no backend route`);
      assert.ok(
        !source.includes("predict_proba"),
        `${file}: no model execution`,
      );
    }
    assert.ok(!/normalize/i.test(ALL_COPY), "no probability normalization");
  });

  it("language red-team rejects unsupported claims", () => {
    const lower = ALL_COPY.toLowerCase();
    for (const phrase of [
      "best model",
      "most accurate model",
      "perfect calibration",
      "leakage free",
      "zero leakage",
      "probability contribution",
      "production-scale",
      "real-time f1",
      "live model",
      "ai-powered",
      "race win distribution",
      "feature caused",
      "reason driver won",
    ]) {
      assert.ok(!lower.includes(phrase), `banned phrase present: ${phrase}`);
    }
  });
});
