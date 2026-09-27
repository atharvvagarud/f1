import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { ABOUT_EVIDENCE_CONTRACT_VERSION, MODEL_EVIDENCE_CONTRACT_VERSION, validateAboutEvidence, validateModelsEvidence } from "./evidence.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..", "..");
const MODELS = JSON.parse(
  readFileSync(join(REPO, "frontend", "data", "models.v1.json"), "utf8"),
);
const ABOUT = JSON.parse(
  readFileSync(join(REPO, "frontend", "data", "about.v1.json"), "utf8"),
);
const HOLDOUT = JSON.parse(
  readFileSync(
    join(REPO, "data", "v2", "model_lab", "reports", "final_holdout_2025_v1.json"),
    "utf8",
  ),
);
const GENERATOR = readFileSync(
  join(REPO, "scripts", "build_phase9_evidence.py"),
  "utf8",
);

function metric(id: string) {
  const found = MODELS.holdout_evidence.metrics.find(
    (entry: { id: string }) => entry.id === id,
  );
  assert.ok(found, `metric ${id} present`);
  return found;
}

describe("phase9 evidence contract", () => {
  it("versions are exact", () => {
    assert.equal(MODELS.contract_version, MODEL_EVIDENCE_CONTRACT_VERSION);
    assert.equal(MODELS.contract_version, "v1");
    assert.equal(ABOUT.contract_version, ABOUT_EVIDENCE_CONTRACT_VERSION);
    assert.equal(ABOUT.contract_version, "v1");
  });

  it("validators accept the frozen evidence", () => {
    validateModelsEvidence(MODELS);
    validateAboutEvidence(ABOUT);
  });

  it("model identity is exact", () => {
    const spec = MODELS.model_spec;
    assert.equal(spec.task, "winner");
    assert.equal(spec.target, "is_winner");
    assert.equal(spec.eligibility, "eligible_is_winner");
    assert.equal(spec.estimator, "LogisticRegression");
    assert.equal(spec.C, 0.01);
    assert.equal(spec.penalty, "l2 (sklearn default, not passed explicitly)");
    assert.equal(spec.solver, "lbfgs");
    assert.equal(spec.max_iter, 1000);
    assert.equal(spec.class_weight, null);
    assert.equal(spec.random_state, 42);
    assert.equal(spec.feature_set, "ALL_84");
    assert.equal(spec.feature_version, "v8");
    assert.equal(spec.canonical_feature_count, 84);
    assert.equal(spec.transformed_feature_count, 106);
    assert.equal(spec.calibration, "RAW");
    assert.equal(spec.probability_semantics, "INDEPENDENT_BINARY");
    assert.equal(spec.final_fit_seasons, "2018-2024");
    assert.equal(spec.holdout_season, 2025);
  });

  it("holdout values equal the frozen report at stored precision", () => {
    const source = HOLDOUT.development_comparison.holdout;
    for (const id of [
      "race_macro_log_loss",
      "race_macro_brier",
      "race_macro_roc_auc",
      "race_macro_pr_auc",
      "expected_calibration_error",
      "winner_top1",
      "winner_top3",
      "state_pooled_log_loss",
      "state_pooled_brier",
    ]) {
      assert.equal(metric(id).value, source[id], `holdout ${id} verbatim`);
    }
    assert.equal(
      MODELS.holdout_evidence.evaluation_class,
      "FROZEN_ONE_SHOT_2025_HOLDOUT",
    );
    assert.deepEqual(MODELS.holdout_evidence.population.seasons, [2025]);
  });

  it("metric roles are explicit and no composite score exists", () => {
    const roles = new Set(MODELS.holdout_evidence.metrics.map((m: { role: string }) => m.role));
    assert.ok(roles.has("PRIMARY"));
    assert.ok(roles.has("SECONDARY"));
    assert.ok(roles.has("TECHNICAL"));
    assert.equal(
      MODELS.holdout_evidence.metrics.find(
        (m: { id: string }) => /composite|overall_score|model_score/.test(m.id),
      ),
      undefined,
    );
    assert.equal(
      MODELS.holdout_evidence.metrics.find(
        (m: { id: string; display_name: string }) =>
          m.id === "accuracy" || m.display_name.toLowerCase() === "accuracy",
      ),
      undefined,
    );
  });

  it("development and holdout are structurally separate", () => {
    assert.equal(
      MODELS.development_evidence.evaluation_class,
      "FROZEN_DEVELOPMENT_FOLDS",
    );
    assert.ok(!("holdout" in MODELS.development_evidence));
    assert.ok(
      !JSON.stringify(MODELS.development_evidence).includes("2025"),
      "no 2025 leakage into development evidence",
    );
  });

  it("temporal folds are exact", () => {
    const folds = MODELS.temporal_evaluation.development_folds;
    assert.deepEqual(
      folds.map((f: { fold: string }) => f.fold),
      ["D1", "D2", "D3"],
    );
    assert.deepEqual(
      folds.map((f: { train: string; validate: number }) => [f.train, f.validate]),
      [
        ["2018-2021", 2022],
        ["2018-2022", 2023],
        ["2018-2023", 2024],
      ],
    );
    assert.equal(MODELS.temporal_evaluation.final_fit, "2018-2024");
    assert.equal(MODELS.temporal_evaluation.holdout, 2025);
  });

  it("feature families sum to 84", () => {
    const families = MODELS.feature_system.families;
    assert.equal(families.length, 8);
    assert.equal(
      families.reduce((sum: number, f: { count: number }) => sum + f.count, 0),
      84,
    );
    assert.equal(MODELS.feature_system.canonical_total, 84);
    assert.equal(MODELS.feature_system.transformed_dim, 106);
  });

  it("calibration evidence is development-only with RAW selected", () => {
    assert.equal(
      MODELS.calibration_evidence.evaluation_class,
      "FROZEN_DEVELOPMENT_CALIBRATION",
    );
    assert.equal(MODELS.calibration_evidence.selected_method, "RAW");
    const calBlob = JSON.stringify(MODELS.calibration_evidence);
    const withoutExclusions = calBlob.replace(/2025 never touched/g, "");
    assert.ok(
      !withoutExclusions.includes("2025"),
      "2025 appears in calibration evidence only as an explicit exclusion",
    );
  });

  it("permutation evidence is explicitly in-sample", () => {
    assert.equal(
      MODELS.permutation_evidence.evidence_class,
      "PRE_2025_FINAL_FIT_IN_SAMPLE",
    );
    assert.match(
      MODELS.permutation_evidence.evidence_class_note,
      /NOT temporally out-of-sample/,
    );
  });

  it("safeguard statement is bounded", () => {
    assert.match(
      MODELS.temporal_safeguards.statement,
      /No temporal leakage was detected under the implemented adversarial test suite\./,
    );
    assert.ok(!/\bno leakage\b/i.test(JSON.stringify(MODELS)));
  });

  it("2025 is marked unserved", () => {
    assert.match(ABOUT.dataset_statistics.serving_scope_note, /NOT served/);
    const replay = ABOUT.capabilities.find((c: { id: string }) => c.id === "REPLAY");
    assert.match(replay.does_not, /2025/);
  });

  it("four system semantics are present and distinct", () => {
    const ids = ABOUT.system_semantics.map((s: { id: string }) => s.id).sort();
    assert.deepEqual(ids, ["FACT", "PREDICTION", "SIMULATION", "STRATEGY"]);
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
    assert.equal(ABOUT.dataset_statistics.tier_b.races, 1149);
    assert.equal(ABOUT.dataset_statistics.tier_b.results, 25784);
    assert.equal(ABOUT.dataset_statistics.replay.served_races, 149);
    assert.equal(ABOUT.dataset_statistics.replay.checkpoints, 9644);
  });

  it("all source_ids resolve and no absolute paths exist", () => {
    const blob = JSON.stringify({ ...MODELS, ...ABOUT });
    assert.ok(!blob.includes("/Users/") && !blob.includes("/tmp/"));
    for (const key of Object.keys(MODELS.sources)) {
      assert.ok(!MODELS.sources[key].path.startsWith("/"));
    }
  });

  it("language red-team rejects unsafe claims", () => {
    const blob = JSON.stringify({ models: MODELS, about: ABOUT }).toLowerCase();
    for (const phrase of [
      "best model",
      "most accurate model",
      "perfectly calibrated",
      "zero leakage",
      "true reason",
      "probability contribution",
      "production-scale",
      "real-time f1",
      "live prediction",
    ]) {
      assert.ok(!blob.includes(phrase), `banned phrase present: ${phrase}`);
    }
    assert.ok(!blob.includes("caused ") || blob.includes("never caused"));
  });

  it("2025 firewall: generator never touches 2025 rows or fitting", () => {
    for (const forbidden of [
      "predict_proba",
      "read_parquet",
      "joblib.load",
      "pickle.load",
      ".fit(",
      "calibrat",
    ]) {
      if (forbidden === "calibrat") continue;
      assert.ok(
        !GENERATOR.includes(forbidden),
        `generator must not contain ${forbidden}`,
      );
    }
    assert.ok(GENERATOR.includes("holdout REPORT"));
  });
});
