"""M0 tests: Model-Lab handoff + temporal evaluation protocol freeze.

Fast, focused coverage of the frozen protocol, the Phase-2 immutability
boundary, chronological folds, task eligibility, metric/baseline/preprocessing
registries, seed/experiment identity, protocol determinism/drift rejection and
the static non-modeling guard. No estimator is trained, no prediction is
produced and no 2025 target metric is computed.
"""

import hashlib
import json
from pathlib import Path

import pytest

from v2.config import V2Paths
from v2.features.build_matrix import output_dir
from v2.features.registry import FEATURE_SET_VERSION
from v2.labels.contracts import LABEL_SET_VERSION
from v2.model_lab import audit as AUDIT
from v2.model_lab import protocol as P

ROOT = V2Paths.resolve().root
_OUT = output_dir(V2Paths.resolve())
_HAS_ARTIFACT = (_OUT / "manifest.json").exists()

pytestmark = pytest.mark.skipif(
    not _HAS_ARTIFACT, reason="canonical F15 matrix artifact not present")


@pytest.fixture(scope="session")
def paths():
    return V2Paths.resolve()


@pytest.fixture(scope="session")
def freeze(paths):
    return P.verify_phase2_artifacts(paths, verify_content_hash=True)


@pytest.fixture(scope="session")
def matrix(paths):
    from v2.features.build_matrix import load_matrix
    return load_matrix(paths)[0]


@pytest.fixture(scope="session")
def manifest(paths):
    from v2.features.build_matrix import load_matrix
    return load_matrix(paths)[1]


@pytest.fixture(scope="session")
def audit(paths):
    return AUDIT.run_audit(paths, verify_content_hash=False)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- frozen Phase-2 versions / hashes -------------------------------------

def test_frozen_versions_unchanged():
    assert FEATURE_SET_VERSION == "v8"
    assert LABEL_SET_VERSION == "v1"
    assert P.REQUIRED_FEATURE_SET_VERSION == FEATURE_SET_VERSION
    assert P.REQUIRED_LABEL_SET_VERSION == LABEL_SET_VERSION
    assert P.REQUIRED_MATRIX_VERSION == "v1"
    assert P.REQUIRED_ABLATION_CONFIG_VERSION == "v1"
    assert P.MODEL_LAB_PROTOCOL_VERSION == "v1"


def test_phase2_freeze_verified(freeze):
    assert freeze["feature_set_version"] == "v8"
    assert freeze["label_set_version"] == "v1"
    assert freeze["matrix_version"] == "v1"
    assert freeze["rows"] == P.EXPECTED_MATRIX_ROWS == 189420
    assert freeze["columns"] == P.EXPECTED_MATRIX_COLUMNS == 106
    assert freeze["races"] == 173
    assert freeze["content_hash"] == P.EXPECTED_MATRIX_CONTENT_HASH
    assert freeze["content_hash_recomputed"] == P.EXPECTED_MATRIX_CONTENT_HASH
    assert freeze["parquet_sha256"] == P.EXPECTED_MATRIX_PARQUET_SHA256
    assert freeze["manifest_sha256"] == P.EXPECTED_MANIFEST_SHA256
    assert freeze["ablation_config_sha256"] == P.EXPECTED_ABLATION_CONFIG_SHA256


def test_phase2_drift_rejected(manifest):
    for field, bad in (
            ("feature_set_version", "v999"),
            ("label_set_version", "v999"),
            ("matrix_version", "v999"),
            ("content_hash", "0" * 64),
            ("feature_registry_fingerprint", "0" * 64),
            ("label_registry_fingerprint", "0" * 64),
            ("row_count", 1),
            ("race_count", 1),
            ("season_range", [2019, 2025])):
        injected = dict(manifest)
        injected[field] = bad
        with pytest.raises(P.ModelLabProtocolError):
            P.validate_manifest_contract(injected)
    bad_task = json.loads(json.dumps(manifest))
    bad_task["task_contract"]["winner"] = ["is_winner", "eligible_wrong"]
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_manifest_contract(bad_task)


def test_ablation_drift_rejected(paths):
    ablation = json.loads(
        (_OUT / "ablation_config.json").read_text())
    P.validate_ablation_contract(ablation)
    injected = dict(ablation)
    injected["config_hash"] = "0" * 64
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_ablation_contract(injected)


# --- chronology / folds / holdout -----------------------------------------

def test_race_chronology_frozen(matrix):
    chronology = AUDIT.build_race_chronology(matrix)
    assert len(chronology) == 173
    assert sorted(chronology["season"].astype(int).unique().tolist()) \
        == list(range(2018, 2026))
    assert list(chronology.columns) == list(P.CHRONOLOGY_KEY)


def test_development_folds_chronological(audit):
    P.validate_folds()
    season = {f.fold_id: f.validation_season for f in P.DEVELOPMENT_FOLDS}
    assert season == {"D1": 2022, "D2": 2023, "D3": 2024}
    for fold in P.DEVELOPMENT_FOLDS:
        assert max(fold.train_seasons) < fold.validation_season
        assert P.PROTECTED_HOLDOUT_SEASON not in fold.train_seasons
        assert fold.validation_season != P.PROTECTED_HOLDOUT_SEASON
    audits = {r["fold_id"]: r for r in audit["development_folds"]}
    assert set(audits) == {"D1", "D2", "D3"}
    for record in audits.values():
        assert record["train_seasons"][-1] < record["validation_season"]


def test_fold_drift_rejected():
    bad = P.DevelopmentFold("X", (2018, 2019, 2020, 2021, 2022), 2022)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_fold(bad)
    leaked = P.DevelopmentFold(
        "Y", (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025), 2024)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_fold(leaked)
    holdout_val = P.DevelopmentFold("Z", (2018, 2019), 2025)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_fold(holdout_val)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_folds(P.DEVELOPMENT_FOLDS
                         + (P.DevelopmentFold("D1", (2018,), 2022),))


def test_holdout_excluded_from_development(audit):
    for record in audit["development_folds"]:
        assert record["validation_season"] != 2025
        assert 2025 not in record["train_seasons"]


def test_final_fit_chronology(audit):
    final = audit["final_boundaries"]
    assert final["final_fit_seasons"] == list(range(2018, 2025))
    assert final["final_fit_races"] == 149
    assert final["final_fit_states"] == 162728
    assert final["holdout_season"] == 2025
    assert final["holdout_races"] == 24
    assert final["holdout_states"] == 26692


def test_split_policy_rejects_random():
    P.validate_split_policy("expanding_window_race_chronology")
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_split_policy("random_row_split")
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_split_policy("shuffled_train_test_split")


# --- task eligibility / masks ---------------------------------------------

def test_task_masks_used_not_ad_hoc(audit):
    totals = audit["task_eligibility_total"]
    assert totals["winner"]["eligible"] == 189420
    assert totals["final_position"]["eligible"] == 178963
    assert totals["final_position"]["coverage"] == 178963
    assert totals["gain"]["eligible"] == 189126
    assert totals["loss"]["eligible"] == 189126
    assert totals["position_change"]["eligible"] == 189126
    P.validate_task_contract()


def test_ordinal_safety():
    spec = P.TASK_SPECS["final_position"]
    assert spec.eligibility_mask == "eligible_ordinal_final_position"
    assert spec.label_column == "final_position"
    assert spec.eligibility_mask != f"{spec.label_column}.notna()"


def test_position_change_mask_is_frozen_phase2_mask():
    spec = P.TASK_SPECS["position_change"]
    assert spec.label_column == "position_change_from_state"
    assert spec.eligibility_mask == "eligible_gain_loss"


def test_primary_and_deferred_tasks():
    assert P.PRIMARY_TASK == "winner"
    assert P.TASK_SPECS["winner"].tier is P.TaskTier.PRIMARY
    assert P.TASK_SPECS["dnf"].tier is P.TaskTier.DEFERRED
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_task("dnf")
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_task("not_a_task")


def test_fold_task_counts_pinned(audit):
    folds = {r["fold_id"]: r for r in audit["development_folds"]}
    assert (folds["D1"]["train_races"], folds["D1"]["validation_races"]) \
        == (81, 22)
    assert (folds["D2"]["train_races"], folds["D2"]["validation_races"]) \
        == (103, 22)
    assert (folds["D3"]["train_races"], folds["D3"]["validation_races"]) \
        == (125, 24)
    assert folds["D1"]["train_states"] == 88123
    assert folds["D1"]["validation_states"] == 23577
    assert folds["D3"]["train_states"] == 136122
    assert folds["D3"]["validation_states"] == 26606
    assert folds["D3"]["validation_tasks"]["winner"]["positives"] == 1444
    assert folds["D3"]["validation_tasks"]["winner"]["eligible"] == 26606


def test_stage_buckets_pinned(audit):
    stages = audit["stage_buckets"]
    assert stages == {"EARLY": 64016, "MID": 63437, "LATE": 61967,
                      "total": 189420}


# --- metrics / baselines / preprocessing / calibration / seeds ------------

def test_metric_registry():
    contract = P.metrics_contract()
    assert contract["binary_primary"] == ["log_loss", "brier"]
    assert "roc_auc" in contract["binary_secondary"]
    assert contract["accuracy_headline_forbidden"] is True
    assert contract["ece"] == {"n_bins": 10, "binning": "equal_width"}
    for name in P.METRIC_REGISTRY:
        P.validate_metric(name)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_metric("accuracy")


def test_baseline_registry():
    names = set(P.BASELINE_NAMES)
    assert {"CURRENT_LEADER", "CURRENT_ORDER", "GRID_POLE", "RECENT_PACE",
            "CLASS_PRIOR"} <= names
    for name in P.BASELINE_NAMES:
        P.validate_baseline(name)
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_baseline("NOPE")
    assert "CURRENT_ORDER_ONLY" in P.FEATURE_SETS_NOT_BASELINES


def test_preprocessing_and_missingness_boundaries():
    assert P.PREPROCESSING_POLICY["fit_scope"] == "training only"
    assert P.PREPROCESSING_POLICY["global_fit_forbidden"] is True
    assert P.PREPROCESSING_POLICY["target_aware_forbidden"] is True
    assert P.MISSINGNESS_POLICY["structural_missingness_preserved"] is True
    assert P.MISSINGNESS_POLICY["global_fill_forbidden"] is True


def test_calibration_boundaries():
    assert set(P.CALIBRATION_METRICS) <= set(P.METRIC_REGISTRY)
    assert P.ECE_N_BINS == 10
    assert P.PROBABILITY_SEMANTICS["post_hoc_normalization"].startswith(
        "forbidden")


def test_within_season_evaluation_not_adopted():
    policy = P.WITHIN_SEASON_EVALUATION
    assert policy["adopted"] is False
    assert policy["classification"].startswith("SECONDARY")
    assert policy["runs_in_m0"] is False


def test_seed_policy_determinism():
    assert P.SEED_POLICY["project_seed"] == 42
    assert P.SEED_POLICY["seed_averaging_by_default"] is False
    assert P.validate_seed(42) == 42
    for bad in (-1, 1.5, True):
        with pytest.raises(P.ModelLabProtocolError):
            P.validate_seed(bad)


# --- feature-set contract --------------------------------------------------

def test_feature_set_vocabulary_and_resolution(manifest):
    vocab = P.feature_set_vocabulary()
    for required in ("ALL_84", "CURRENT_ORDER_ONLY", "MINIMAL_RACE_STATE"):
        assert required in vocab
    assert any(n.startswith("CUMULATIVE_") for n in vocab)
    assert any(n.startswith("ALL_MINUS_") for n in vocab)
    assert P.validate_feature_set_name("ALL_84", manifest) \
        == tuple(manifest["predictive_columns"])
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_feature_set_name("NOT_A_SET", manifest)


# --- experiment identity / schema / holdout access ------------------------

def _config(**over):
    base = {
        "experiment_id": "x", "protocol_version": P.MODEL_LAB_PROTOCOL_VERSION,
        "git_commit": "deadbeef", "phase2_freeze_commit": P.PHASE2_FREEZE_COMMIT,
        "feature_set_version": "v8", "label_set_version": "v1",
        "matrix_version": "v1", "ablation_config_version": "v1",
        "matrix_content_hash": P.EXPECTED_MATRIX_CONTENT_HASH,
        "feature_set": "ALL_84", "task": "winner", "fold": "D1",
        "model_family": "logistic_regression", "model_parameters": {},
        "preprocessing_config": {}, "calibration_config": {}, "seed": 42,
        "training_rows": 1, "training_races": 1, "validation_rows": 1,
        "validation_races": 1, "split_policy":
            "expanding_window_race_chronology", "holdout_accessed": False,
    }
    base.update(over)
    return base


def test_experiment_config_validation():
    P.validate_experiment_config(_config())
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_experiment_config(_config(task="nope"))
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_experiment_config(_config(split_policy="random_row_split"))
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_experiment_config(_config(holdout_accessed="yes"))
    missing = _config()
    del missing["seed"]
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_experiment_config(missing)


def test_experiment_id_deterministic():
    a = P.experiment_id(_config(seed=42))
    b = P.experiment_id(_config(seed=42))
    c = P.experiment_id(_config(seed=43))
    assert a == b
    assert a != c
    assert len(a) == 64


def test_holdout_access_metadata():
    assert P.holdout_access_metadata(False, "")["holdout_accessed"] is False
    meta = P.holdout_access_metadata(True, "final locked evaluation")
    assert meta["holdout_accessed"] is True
    assert meta["holdout_protocol_version"] == P.MODEL_LAB_PROTOCOL_VERSION
    with pytest.raises(P.ModelLabProtocolError):
        P.holdout_access_metadata(True, "")
    with pytest.raises(P.ModelLabProtocolError):
        P.holdout_access_metadata("yes", "x")


# --- deterministic protocol artifact / drift ------------------------------

def test_protocol_hash_deterministic(tmp_path):
    r1 = P.render_protocol()
    r2 = P.render_protocol()
    assert r1 == r2
    doc = json.loads(r1)
    P.validate_protocol_document(doc)
    assert doc["protocol_semantic_hash"] == P.protocol_semantic_hash()
    dest = P.write_protocol(tmp_path / "protocol.json")
    assert dest.read_text() == r1
    assert json.loads(dest.read_text())["protocol_version"] == "v1"


def test_protocol_drift_rejected():
    doc = P.protocol_document()
    tampered = json.loads(json.dumps(doc))
    tampered["primary_task"] = "podium"
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_protocol_document(tampered)
    bad_version = json.loads(json.dumps(doc))
    bad_version["protocol_version"] = "v2"
    with pytest.raises(P.ModelLabProtocolError):
        P.validate_protocol_document(bad_version)


def test_committed_protocol_artifact_matches():
    path = ROOT / P.PROTOCOL_REL_PATH
    if not path.exists():
        pytest.skip("protocol artifact not exported yet")
    doc = json.loads(path.read_text())
    P.validate_protocol_document(doc)


# --- static non-modeling guard --------------------------------------------
#
# M3/M4/M5 scope note: M3 intentionally introduces the single permitted
# estimator (LogisticRegression reference), M4 the two permitted nonlinear
# candidates (HistGradientBoosting, XGBoost) and M5 the two permitted bagged
# candidates (ExtraTrees, RandomForest) in the stage-owned modules listed
# below. Those files are excluded from this M0-era guard; the M3/M4/M5 test
# modules own the stricter successor guards (only the stage's declared
# families may train; every other family stays forbidden). All pre-M3
# framework files remain fully guarded.
M3_OWNED_MODULES = frozenset({
    "preprocessing.py", "logreg.py", "model_runner.py", "model_suite.py",
    "run_models.py",
    "tree_candidates.py", "nonlinear_runner.py", "nonlinear_suite.py",
    "run_nonlinear.py",
    "bagged_candidates.py", "bagged_runner.py", "bagged_suite.py",
    "run_bagged.py",
    # M6 stage-owned modules (LogReg + ExtraTrees tuning); the M6 test module
    # owns the stricter successor guard forbidding every other family.
    "inner_splits.py", "tuning.py", "tuning_candidates.py",
    "tuning_runner.py", "tuning_suite.py", "run_tuning.py",
    # M7 stage-owned modules (LogReg regularization boundary resolution); the
    # M7 test module owns the stricter successor guard.
    "logreg_boundary.py", "run_boundary.py",
    # M8 stage-owned modules (Platt + isotonic calibration evaluation); the M8
    # test module owns the stricter successor guard.
    "calibration_selection.py", "run_calibration.py",
    # M9 stage-owned modules (final LogReg fit + one-shot protected holdout);
    # the M9 test module owns the stricter successor guard.
    "final_fit.py", "run_final.py",
    # P3.1 production-owned module (frozen inference only: validated load +
    # batch predict_proba, no fitting); the P3.1 test module owns the
    # stricter successor guard (no .fit(, no holdout access).
    "serving.py",
})


def test_no_estimator_or_metric_source():
    forbidden = (".fi" + "t(", ".pre" + "dict(", ".predict_" + "proba(",
                 "from sk" + "learn", "import sk" + "learn",
                 "import xg" + "boost", "import light" + "gbm",
                 "import cat" + "boost", "import torch", "log_l" + "oss(",
                 "brier_" + "score(")
    for path in sorted((ROOT / "v2" / "model_lab").glob("*.py")):
        if path.name in M3_OWNED_MODULES:
            continue
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name}: forbidden {token!r}"
