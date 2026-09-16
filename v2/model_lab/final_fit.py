"""M9 final development fit + one-shot protected 2025 holdout evaluation.

This is the Model Lab freeze stage. The development process already selected
and froze ONE configuration *without* using 2025 target performance: the M7
global Logistic Regression specification ``C=0.01`` with the M8 ``RAW``
calibration decision. M9 does not tune, select, calibrate, threshold or
otherwise repair anything.

Responsibilities:

1. verify the complete frozen development specification (pre-unlock gate);
2. write the immutable PRE-UNLOCK declaration before touching 2025 labels;
3. fit the frozen pipeline once on ALL eligible 2018-2024 rows;
4. verify final-fit determinism on a fixed DEVELOPMENT fixture and retain one
   equivalent model;
5. unlock 2025 exactly once (explicit opt-in) and evaluate the frozen model
   through the existing canonical evaluation machinery;
6. write the protected holdout artifact, the canonical protected experiment,
   the final-model metadata descriptor and the freeze documents.

The 2025 holdout result is REPORTING evidence only. Nothing here may change
the model, features, preprocessing, calibration, labels, masks, metrics,
thresholds, split rules or aggregation after the holdout is revealed.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from v2.config import V2Paths
from v2.model_lab import data as DATA
from v2.model_lab import experiment as EX
from v2.model_lab import preprocessing as PRE
from v2.model_lab import results as RES
from v2.model_lab import runner as RUN
from v2.model_lab import splits as SPLITS
from v2.model_lab import stages as STAGES
from v2.model_lab import tasks as TASKS
from v2.model_lab import timing as TIMING
from v2.model_lab import tuning_candidates as TC
from v2.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutAlreadyConsumed,
    ProtectedHoldoutError,
)
from v2.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)
from v2.model_lab.protocol import (
    EXPECTED_ABLATION_CONFIG_SHA256,
    EXPECTED_FEATURE_REGISTRY_FINGERPRINT,
    EXPECTED_LABEL_REGISTRY_FINGERPRINT,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_MATRIX_CONTENT_HASH,
    EXPECTED_MATRIX_PARQUET_SHA256,
    EXPECTED_MATRIX_SCHEMA_HASH,
    MODEL_LAB_PROTOCOL_VERSION,
    PROTECTED_HOLDOUT_SEASON,
    REQUIRED_ABLATION_CONFIG_VERSION,
    REQUIRED_FEATURE_SET_VERSION,
    REQUIRED_LABEL_SET_VERSION,
    REQUIRED_MATRIX_VERSION,
    protocol_semantic_hash,
    verify_phase2_artifacts,
)

# --- frozen M9 contract -------------------------------------------------------

M9_TASK = "winner"
M9_FEATURE_SET = "ALL_84"
M9_SEED = 42

#: M7-frozen regularization; M9 never retunes it.
FROZEN_C = 0.01
SOLVER = "lbfgs"
MAX_ITER = 1000
CLASS_WEIGHT = None
RANDOM_STATE = 42

#: Final-fit / protected-holdout temporal contract.
FINAL_FIT_SEASONS = tuple(range(2018, 2025))
HOLDOUT_SEASON = PROTECTED_HOLDOUT_SEASON

#: Canonical count anchors (verified against the frozen matrix; drift is fatal).
FINAL_FIT_EXPECTED = {
    "races": 149, "states": 162728, "eligible": 162728,
    "positives": 8926, "negatives": 153802,
}
HOLDOUT_EXPECTED = {
    "races": 24, "states": 26692, "eligible": 26692,
    "positives": 1444, "negatives": 25248,
}

#: Distinct protected experiment family (never overwrites a development id).
PROTECTED_EXPERIMENT_FAMILY = "logistic_regression_final_raw"

#: Artifact names (generated, gitignored under data/v2).
SUITE_SCHEMA_VERSION = "v1"
PREUNLOCK_FILENAME = "m9_preunlock_freeze_v1.json"
FINAL_HOLDOUT_FILENAME = "final_holdout_2025_v1.json"
FINAL_MODEL_NAME = "winner_logreg_raw_v1"
M7_ARTIFACT_FILENAME = "logreg_boundary_resolution_v1.json"
M8_ARTIFACT_FILENAME = "calibration_selection_v1.json"

#: Immutable Phase-2/M0 boundary artifacts byte-hashed for the artifacts.
PHASE2_REL = "data/v2/processed/model_matrix/matrix_version=v1"
PROTOCOL_JSON_REL = "docs/generated/model_lab_protocol_v1.json"
FREEZE_MANIFEST_REL = "docs/generated/phase2_freeze_manifest.json"

#: Deterministic whole-race bootstrap (frozen uncertainty policy).
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = EX.PROJECT_SEED

#: Latency probe settings (real measured samples only).
BATCH_LATENCY_REPEATS = 5
SINGLE_STATE_SAMPLE = 200

#: Model-card / final-report output paths (tracked docs).
MODEL_CARD_REL = "docs/MODEL_LAB_FINAL_MODEL_CARD.md"
FINAL_REPORT_REL = "docs/MODEL_LAB_FINAL_REPORT.md"
FREEZE_MANIFEST_OUT_REL = "docs/MODEL_LAB_FREEZE_MANIFEST.json"

#: Gitignored final-model metadata directory (no opaque estimator blob).
FINAL_MODEL_DIR_REL = "data/v2/model_lab/final"


# --- small deterministic helpers ---------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_json(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else float(value)
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    return value


def _base_dir(paths=None, root=None) -> Path:
    if root is not None:
        return Path(root)
    if paths is not None:
        return Path(paths.root)
    return V2Paths.resolve().root


def reports_dir(paths=None, root=None) -> Path:
    return _base_dir(paths, root) / "data/v2/model_lab/reports"


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / FINAL_HOLDOUT_FILENAME


def preunlock_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / PREUNLOCK_FILENAME


def m7_artifact_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / M7_ARTIFACT_FILENAME


def m8_artifact_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / M8_ARTIFACT_FILENAME


def final_model_dir(paths=None, root=None) -> Path:
    return _base_dir(paths, root) / FINAL_MODEL_DIR_REL / FINAL_MODEL_NAME


def _peak_rss_bytes():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, AttributeError):
        return None


# --- frozen specification + fingerprint --------------------------------------


def frozen_model_parameters() -> dict:
    """Resolved estimator parameters recorded in experiment identity."""
    return {
        "estimator": "LogisticRegression",
        "penalty": "l2 (sklearn default, not passed explicitly)",
        "C": FROZEN_C,
        "solver": SOLVER,
        "max_iter": MAX_ITER,
        "class_weight": CLASS_WEIGHT,
        "random_state": RANDOM_STATE,
        "feature_set": M9_FEATURE_SET,
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": "INDEPENDENT_BINARY",
        "calibration_method": "RAW",
    }


def frozen_specification() -> dict:
    """The complete immutable scientific specification for M9.

    Deterministic: contains no timestamps, paths, machine facts or results.
    """
    return {
        "task": M9_TASK,
        "target": "is_winner",
        "eligibility_mask": "eligible_is_winner",
        "feature_set": M9_FEATURE_SET,
        "feature_count": 84,
        "model_family": "logistic_regression",
        "estimator": "LogisticRegression",
        "penalty": "l2 (sklearn default, not passed explicitly)",
        "C": FROZEN_C,
        "solver": SOLVER,
        "max_iter": MAX_ITER,
        "class_weight": CLASS_WEIGHT,
        "random_state": RANDOM_STATE,
        "preprocessing": PRE.preprocessing_contract_dict(),
        "calibration_method": "RAW",
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": "INDEPENDENT_BINARY",
        "weighting": "state_equal",
        "resampling": False,
        "final_fit_seasons": list(FINAL_FIT_SEASONS),
        "holdout_season": HOLDOUT_SEASON,
        "seed": M9_SEED,
        "selection_references": {
            "m7": "logreg_boundary_resolution_v1.json "
                  "(global development C=0.01)",
            "m8": "calibration_selection_v1.json "
                  "(selected calibration method RAW)",
            "protocol": "docs/generated/model_lab_protocol_v1.json",
        },
    }


def specification_fingerprint() -> str:
    """Deterministic SHA-256 over the canonical frozen specification."""
    return _sha256_json(frozen_specification())


def build_frozen_estimator():
    """Construct exactly the frozen LogisticRegression (no other family)."""
    estimator = TC.build_estimator(TC.LOGREG_FAMILY, {"C": FROZEN_C})
    from sklearn.linear_model import LogisticRegression
    if not isinstance(estimator, LogisticRegression):
        raise ExperimentConfigError(
            "frozen estimator construction did not yield LogisticRegression")
    return estimator


def _estimator_parameters(estimator) -> dict:
    return {
        "class_name": type(estimator).__name__,
        "C": float(estimator.C),
        "solver": estimator.solver,
        "max_iter": int(estimator.max_iter),
        "class_weight": estimator.class_weight,
        "random_state": estimator.random_state,
    }


# --- immutable boundary hash report ------------------------------------------


def immutability_report(paths=None, root=None) -> dict:
    base = _base_dir(paths, root)
    out = base / PHASE2_REL
    return {
        "phase2_parquet_byte_hash": _sha256_file(out / "model_matrix.parquet"),
        "phase2_manifest_byte_hash": _sha256_file(out / "manifest.json"),
        "f16_ablation_byte_hash": _sha256_file(out / "ablation_config.json"),
        "phase2_matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "phase2_matrix_schema_hash": EXPECTED_MATRIX_SCHEMA_HASH,
        "feature_registry_fingerprint": EXPECTED_FEATURE_REGISTRY_FINGERPRINT,
        "label_registry_fingerprint": EXPECTED_LABEL_REGISTRY_FINGERPRINT,
        "m0_protocol_semantic_hash": protocol_semantic_hash(),
        "m0_protocol_json_byte_hash": _sha256_file(base / PROTOCOL_JSON_REL),
        "phase2_freeze_manifest_byte_hash": _sha256_file(
            base / FREEZE_MANIFEST_REL),
        "expected": {
            "phase2_matrix_parquet_sha256": EXPECTED_MATRIX_PARQUET_SHA256,
            "phase2_manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "f16_ablation_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        },
    }


# --- pre-unlock gate ----------------------------------------------------------


def run_preunlock_gate(canonical: DATA.CanonicalMatrix | None = None, *,
                       paths=None, root=None,
                       verify_hashes: bool = True) -> dict:
    """Smallest set of checks that must pass before 2025 is unlocked.

    Raises ``ExperimentConfigError`` listing every failed condition. Never
    touches 2025 labels.
    """
    base = _base_dir(paths, root)
    failures: list = []
    checks: dict = {}

    # 1. M7 configuration artifact.
    try:
        m7 = json.loads(m7_artifact_path(paths, root).read_text())
        checks["m7_artifact_readable"] = True
        checks["m7_frozen_c"] = float(
            m7["global_configuration"]["frozen_specification"]["C"])
        checks["m7_boundary_status"] = m7["boundary_status"]["status"]
        checks["m7_holdout_accessed"] = m7.get("holdout_accessed")
    except (OSError, KeyError, ValueError) as exc:
        checks["m7_artifact_readable"] = False
        failures.append(f"M7 artifact unreadable: {exc}")

    # 2. M8 calibration artifact.
    try:
        m8 = json.loads(m8_artifact_path(paths, root).read_text())
        checks["m8_artifact_readable"] = True
        checks["m8_selected_method"] = m8["method_comparison"][
            "selected_method"]
        checks["m8_frozen_c"] = float(m8["frozen_c"])
        checks["m8_holdout_accessed"] = m8.get("holdout_accessed")
    except (OSError, KeyError, ValueError) as exc:
        checks["m8_artifact_readable"] = False
        failures.append(f"M8 artifact unreadable: {exc}")

    # 3. Frozen feature/temporal contract.
    checks["task"] = M9_TASK
    checks["feature_set"] = M9_FEATURE_SET
    checks["final_fit_seasons"] = list(FINAL_FIT_SEASONS)
    checks["holdout_season"] = HOLDOUT_SEASON
    checks["probability_kind"] = "BINARY_PROBABILITY"
    checks["probability_semantics"] = "INDEPENDENT_BINARY"
    checks["calibration_method"] = "RAW"

    # 4. Protective 2025 firewall is still closed without opt-in.
    blocked_split = False
    try:
        SPLITS.get_split(SPLITS.HOLDOUT_ID)
    except ProtectedHoldoutError:
        blocked_split = True
    checks["holdout_blocked_without_opt_in"] = blocked_split
    blocked_runner = False
    try:
        RUN.resolve_development_fold(SPLITS.HOLDOUT_ID)
    except ProtectedHoldoutError:
        blocked_runner = True
    checks["development_runner_rejects_holdout"] = blocked_runner

    # 5. Frozen Phase-2/M0 hashes unchanged.
    if verify_hashes:
        try:
            checks["phase2_verification"] = verify_phase2_artifacts(
                paths if paths is not None else V2Paths.resolve(),
                verify_content_hash=(canonical is not None),
                verify_bytes=True)
        except Exception as exc:  # noqa: BLE001 - surfaced as a gate failure
            checks["phase2_verification"] = {"error": str(exc)}
            failures.append(f"Phase-2 frozen hash verification failed: {exc}")
    else:
        checks["phase2_verification"] = {"status": "SKIPPED"}

    # 6. Estimator construction exactly matches the frozen spec.
    estimator = build_frozen_estimator()
    resolved = _estimator_parameters(estimator)
    checks["estimator_parameters"] = resolved
    if abs(resolved["C"] - FROZEN_C) > 1e-12:
        failures.append(f"estimator C {resolved['C']} != {FROZEN_C}")
    if resolved["solver"] != SOLVER:
        failures.append(f"estimator solver {resolved['solver']} != {SOLVER}")
    if resolved["max_iter"] != MAX_ITER:
        failures.append(f"estimator max_iter {resolved['max_iter']}")
    if resolved["class_weight"] is not CLASS_WEIGHT:
        failures.append(f"estimator class_weight {resolved['class_weight']}")
    if resolved["random_state"] != RANDOM_STATE:
        failures.append(f"estimator random_state {resolved['random_state']}")

    # 7. Artifact-value assertions.
    if checks.get("m7_frozen_c") is not None \
            and abs(checks["m7_frozen_c"] - FROZEN_C) > 1e-12:
        failures.append(f"M7 frozen C {checks['m7_frozen_c']} != {FROZEN_C}")
    if checks.get("m7_boundary_status") != "RESOLVED":
        failures.append("M7 boundary status is not RESOLVED")
    if checks.get("m7_holdout_accessed") is not False:
        failures.append("M7 reports holdout access")
    if checks.get("m8_selected_method") != "RAW":
        failures.append(
            f"M8 selected method {checks.get('m8_selected_method')} != RAW")
    if checks.get("m8_frozen_c") is not None \
            and abs(checks["m8_frozen_c"] - FROZEN_C) > 1e-12:
        failures.append(f"M8 frozen C {checks['m8_frozen_c']} != {FROZEN_C}")
    if checks.get("m8_holdout_accessed") is not False:
        failures.append("M8 reports holdout access")
    if not blocked_split:
        failures.append("2025 holdout was not blocked without explicit opt-in")
    if not blocked_runner:
        failures.append("development runner did not reject the holdout")

    if failures:
        raise ExperimentConfigError(
            "M9 pre-unlock gate FAILED; 2025 must not be evaluated: "
            + "; ".join(failures))
    checks["passed"] = True
    checks["specification_fingerprint"] = specification_fingerprint()
    checks["immutability"] = immutability_report(paths, root)
    return checks


# --- pre-unlock declaration ---------------------------------------------------


def build_preunlock_declaration(canonical: DATA.CanonicalMatrix | None = None,
                                *, paths=None, root=None) -> dict:
    """Machine-readable declaration frozen BEFORE any 2025 label access."""
    immutability = immutability_report(paths, root)
    m7_hash = _sha256_file(m7_artifact_path(paths, root))
    m8_hash = _sha256_file(m8_artifact_path(paths, root))
    return {
        "schema_version": SUITE_SCHEMA_VERSION,
        "stage": "M9",
        "title": "Pre-unlock frozen specification declaration",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "matrix_hashes": {
            "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
            "matrix_schema_hash": EXPECTED_MATRIX_SCHEMA_HASH,
            "matrix_version": REQUIRED_MATRIX_VERSION,
            "phase2_parquet_byte_hash": immutability[
                "phase2_parquet_byte_hash"],
            "phase2_manifest_byte_hash": immutability[
                "phase2_manifest_byte_hash"],
            "f16_ablation_byte_hash": immutability["f16_ablation_byte_hash"],
            "m0_protocol_semantic_hash": immutability[
                "m0_protocol_semantic_hash"],
            "m0_protocol_json_byte_hash": immutability[
                "m0_protocol_json_byte_hash"],
            "phase2_freeze_manifest_byte_hash": immutability[
                "phase2_freeze_manifest_byte_hash"],
        },
        "feature_registry_fingerprint": EXPECTED_FEATURE_REGISTRY_FINGERPRINT,
        "label_registry_fingerprint": EXPECTED_LABEL_REGISTRY_FINGERPRINT,
        "m7_artifact_sha256": m7_hash,
        "m8_artifact_sha256": m8_hash,
        "selected_model_family": "logistic_regression",
        "C": FROZEN_C,
        "solver": SOLVER,
        "max_iter": MAX_ITER,
        "class_weight": CLASS_WEIGHT,
        "random_state": RANDOM_STATE,
        "feature_set": M9_FEATURE_SET,
        "preprocessing_specification": PRE.preprocessing_contract_dict(),
        "preprocessing_version": "m3-train-fitted-v1",
        "calibration_method": "RAW",
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": "INDEPENDENT_BINARY",
        "weighting": "state_equal",
        "task": M9_TASK,
        "target": "is_winner",
        "eligibility_mask": "eligible_is_winner",
        "final_fit_seasons": list(FINAL_FIT_SEASONS),
        "holdout_season": HOLDOUT_SEASON,
        "selection_history_references": {
            "m7": M7_ARTIFACT_FILENAME,
            "m8": M8_ARTIFACT_FILENAME,
            "protocol": PROTOCOL_JSON_REL,
        },
        "holdout_target_metrics_evaluated_by_m9": False,
        "holdout_target_metrics_evaluated_statement": (
            "2025 target metrics have NOT been evaluated by M9 at the time "
            "this declaration was written; it is frozen before unlock."),
        "frozen_before_holdout": True,
        "specification": frozen_specification(),
        "specification_fingerprint": specification_fingerprint(),
    }


def write_preunlock_declaration(canonical=None, *, paths=None, root=None,
                                out=None) -> Path:
    """Write the pre-unlock declaration once. Never rewritten afterwards."""
    dest = Path(out) if out is not None else preunlock_path(paths, root)
    if dest.exists():
        raise ExperimentConfigError(
            f"pre-unlock declaration already exists at {dest}; it must never "
            "be modified after 2025 evaluation")
    declaration = build_preunlock_declaration(canonical, paths=paths, root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, declaration)
    return dest


# --- final fit ----------------------------------------------------------------


def _check_counts(observed: dict, expected: dict, label: str) -> None:
    for key, value in expected.items():
        if int(observed.get(key, -1)) != int(value):
            raise ExperimentConfigError(
                f"{label} count drift: {key}={observed.get(key)!r} != "
                f"{value!r}")


def materialize_final_fit(canonical: DATA.CanonicalMatrix):
    """All eligible 2018-2024 winner rows through the frozen mask."""
    dataset = SPLITS.materialize(
        canonical, M9_TASK, SPLITS.FINAL_FIT_ID, M9_FEATURE_SET,
        assert_m0_counts=False)
    if tuple(int(s) for s in dataset.split.train_seasons) != FINAL_FIT_SEASONS:
        raise ExperimentConfigError(
            f"FINAL_FIT train seasons {dataset.split.train_seasons} != "
            f"{FINAL_FIT_SEASONS}")
    if dataset.split.validation_seasons:
        raise ExperimentConfigError("FINAL_FIT must have no validation side")
    if HOLDOUT_SEASON in {int(s) for s in dataset.split.train_seasons}:
        raise ProtectedHoldoutError("2025 leaked into the final-fit train side")
    counts = {
        "races": int(dataset.train_metadata["race_id"].nunique()),
        "states": int(dataset.train_counts["states"]),
        "eligible": int(dataset.train_counts["eligible"]),
        "positives": int(dataset.train_counts["positives"]),
        "negatives": int(dataset.train_counts["eligible"]
                         - dataset.train_counts["positives"]),
    }
    _check_counts(counts, FINAL_FIT_EXPECTED, "FINAL_FIT")
    return dataset, counts


def fit_final_model(canonical: DATA.CanonicalMatrix, dataset=None, *,
                    timings_out: dict | None = None) -> dict:
    """One final fit: frozen train-fitted preprocessing + LogReg C=0.01."""
    if dataset is None:
        dataset, _ = materialize_final_fit(canonical)
    if len(dataset.X_train) == 0:
        raise ExperimentConfigError("FINAL_FIT training side is empty")

    timings: dict = {}
    with TIMING.Timer() as t:
        preprocessor = PRE.fit_preprocessor(dataset.X_train, canonical.schema)
    timings["preprocessing_fit_seconds"] = t.seconds

    model = TC.fit_fresh_model(
        TC.LOGREG_FAMILY, {"C": FROZEN_C}, dataset.X_train, dataset.y_train,
        preprocessor=preprocessor)
    timings["transform_train_seconds"] = model.timing.get(
        "transform_train_seconds")
    timings["estimator_fit_seconds"] = model.timing.get(
        "estimator_fit_seconds")
    if timings_out is not None:
        timings_out.update(timings)
    return {"model": model, "dataset": dataset, "timings": timings}


def final_fit_determinism(canonical: DATA.CanonicalMatrix, *, paths=None,
                          root=None) -> dict:
    """Fit the frozen final pipeline twice; compare on a DEVELOPMENT fixture.

    The protected 2025 holdout is never evaluated here. One of the two
    equivalent models is retained for the single holdout run.
    """
    dataset, counts = materialize_final_fit(canonical)
    first = fit_final_model(canonical, dataset)
    second = fit_final_model(canonical, dataset)

    fixture = SPLITS.materialize(
        canonical, M9_TASK, "D1", M9_FEATURE_SET, assert_m0_counts=False)
    X_fixture = fixture.X_validation
    if int(fixture.validation_metadata["season"].astype(int).max()) \
            >= HOLDOUT_SEASON:
        raise ProtectedHoldoutError("determinism fixture reached 2025")

    p_first = first["model"].predict_positive_probability(X_fixture)
    p_second = second["model"].predict_positive_probability(X_fixture)
    t_first = first["model"].transform(X_fixture)
    t_second = second["model"].transform(X_fixture)
    coef_first = np.asarray(first["model"].estimator.coef_, dtype=float)
    coef_second = np.asarray(second["model"].estimator.coef_, dtype=float)

    return {
        "fixture": "D1 validation season (2022) eligible winner states",
        "fixture_states": int(len(X_fixture)),
        "max_abs_probability_difference": float(
            np.max(np.abs(p_first - p_second))),
        "max_abs_preprocessed_difference": float(
            np.max(np.abs(t_first - t_second))),
        "max_abs_coefficient_difference": float(
            np.max(np.abs(coef_first - coef_second))),
        "identical_transformed_dim": bool(
            t_first.shape == t_second.shape),
        "final_fit_counts": counts,
        "model": first["model"],
        "dataset": dataset,
        "timings": first["timings"],
    }


# --- protected-holdout consumption seal (P3.1) ---------------------------------


def _refuse_if_holdout_consumed(*, paths=None, root=None, out=None) -> None:
    """Mechanical seal: refuse a second sanctioned 2025 evaluation.

    The canonical protected artifact is the durable consumed marker. This
    check runs before any canonical-matrix load or target materialization,
    so a refused call never observes 2025 targets and never overwrites the
    immutable artifact.
    """
    candidates = [default_out(paths, root)]
    if out is not None:
        candidates.append(Path(out))
    for dest in candidates:
        if Path(dest).exists():
            raise ProtectedHoldoutAlreadyConsumed(
                f"protected 2025 holdout already consumed: {dest} exists; "
                "the M9 one-shot evaluation cannot run again and the "
                "artifact must never be overwritten")


# --- holdout evaluation -------------------------------------------------------


def materialize_holdout(canonical: DATA.CanonicalMatrix, *,
                        allow_protected_holdout: bool = False):
    """Materialize the eligible 2025 winner holdout (explicit opt-in only)."""
    if not allow_protected_holdout:
        raise ProtectedHoldoutError(
            "the protected 2025 holdout requires the explicit M9 opt-in "
            "(allow_protected_holdout=True)")
    dataset = SPLITS.materialize(
        canonical, M9_TASK, SPLITS.HOLDOUT_ID, M9_FEATURE_SET,
        allow_protected_holdout=True, assert_m0_counts=False)
    seasons = {int(s) for s in dataset.validation_metadata["season"]}
    if seasons != {HOLDOUT_SEASON}:
        raise ProtectedHoldoutError(
            f"holdout validation seasons {seasons} != {HOLDOUT_SEASON}")
    counts = {
        "races": int(dataset.validation_metadata["race_id"].nunique()),
        "states": int(dataset.validation_counts["states"]),
        "eligible": int(dataset.validation_counts["eligible"]),
        "positives": int(dataset.validation_counts["positives"]),
        "negatives": int(dataset.validation_counts["eligible"]
                         - dataset.validation_counts["positives"]),
    }
    _check_counts(counts, HOLDOUT_EXPECTED, "HOLDOUT")
    return dataset, counts


def _race_macro(result, metric):
    payload = result.metrics.get(metric, {})
    if payload.get("status") != "OK":
        return None
    node = payload.get("race_macro", {})
    return node.get("value"), node.get("per_race", {})


def _state_pooled(result, metric):
    payload = result.metrics.get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("state_pooled", {}).get("value")


def _topk_payload(result) -> dict:
    payload = (result.race_metrics or {}).get("winner_top_k", {})
    if payload.get("status") != "OK":
        return {"status": "NOT_APPLICABLE", "reason": payload.get("reason")}
    return payload


def race_macro_bootstrap(y_true, prob, race_ids, metric: str, *,
                         replicates: int = BOOTSTRAP_REPLICATES,
                         seed: int = BOOTSTRAP_SEED) -> dict:
    """Deterministic whole-race bootstrap of one race-macro metric.

    Whole races are the resampling unit; individual driver-state rows are
    never resampled. Descriptive percentile interval only.
    """
    from v2.model_lab.metrics import METRIC_FUNCTIONS
    fn = METRIC_FUNCTIONS[metric]
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(prob, dtype=float)
    races = sorted(set(str(r) for r in race_ids))
    per = []
    for race in races:
        mask = np.asarray([str(r) == race for r in race_ids])
        value = fn(y[mask], p[mask])
        if value is not None and math.isfinite(float(value)):
            per.append(float(value))
    arr = np.asarray(per, dtype=float)
    if len(arr) == 0:
        return {"status": "NOT_APPLICABLE", "reason": "no defined race"}
    rng = np.random.default_rng(seed)
    n = len(arr)
    boot = np.empty(int(replicates), dtype=float)
    for i in range(int(replicates)):
        idx = rng.integers(0, n, size=n)
        boot[i] = float(np.mean(arr[idx]))
    return {
        "status": "OK",
        "metric": metric,
        "unit": "whole_race",
        "replicates": int(replicates),
        "seed": int(seed),
        "n_races": int(n),
        "point": float(np.mean(arr)),
        "percentiles": {
            "p2_5": float(np.percentile(boot, 2.5)),
            "p50": float(np.percentile(boot, 50.0)),
            "p97_5": float(np.percentile(boot, 97.5)),
        },
        "note": "descriptive percentile interval only; not a significance "
                "claim",
    }


def _reliability_summary(bins) -> dict:
    if not bins:
        return {}
    empty = sum(1 for b in bins if not b["count"])
    gaps = []
    for b in bins:
        if b["count"]:
            gaps.append(abs(b["observed_frequency"] - b["mean_predicted"]))
    return {
        "n_bins": len(bins),
        "empty_bins": int(empty),
        "largest_absolute_gap": float(max(gaps)) if gaps else None,
        "under_confident_bins": int(sum(
            1 for b in bins if b["count"]
            and b["observed_frequency"] > b["mean_predicted"])),
        "over_confident_bins": int(sum(
            1 for b in bins if b["count"]
            and b["observed_frequency"] < b["mean_predicted"])),
    }


def evaluate_protected_holdout(model, canonical: DATA.CanonicalMatrix, *,
                               allow_protected_holdout: bool = False,
                               paths=None, root=None,
                               bootstrap: bool = True) -> dict:
    """The single sanctioned M9 target evaluation of the 2025 holdout."""
    if not allow_protected_holdout:
        raise ProtectedHoldoutError(
            "evaluate_protected_holdout requires allow_protected_holdout=True")
    _refuse_if_holdout_consumed(paths=paths, root=root)
    dataset, counts = materialize_holdout(
        canonical, allow_protected_holdout=True)
    resolved = TASKS.resolve_task(M9_TASK)
    timings: dict = {}

    X_holdout = dataset.X_validation
    val_frame = canonical.frame.loc[dataset.y_validation.index].copy()
    if list(val_frame["state_id"]) != list(
            dataset.validation_metadata["state_id"]):
        raise ExperimentConfigError("holdout identity metadata is misaligned")
    y_true = np.asarray(dataset.y_validation.astype(float).to_numpy(),
                        dtype=float)
    race_ids = np.asarray(dataset.validation_metadata["race_id"].astype(str))

    with TIMING.Timer() as t:
        matrix = model.transform(X_holdout)
    timings["holdout_transform_seconds"] = t.seconds
    with TIMING.Timer() as t:
        values = model.predict_positive_probability(X_holdout)
    timings["holdout_prediction_seconds"] = t.seconds
    if not np.all(np.isfinite(values)):
        raise InvalidPredictionError("holdout predictions contain NaN/inf")

    prediction = PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(val_frame["state_id"]),
        values=np.asarray(values, dtype=float),
        semantics=ProbabilitySemantics.INDEPENDENT_BINARY,
        positive_class=1,
    )
    warnings: list = []

    with TIMING.Timer() as t:
        metric_payloads, w = RUN.evaluate_row_metrics(
            prediction, tuple(resolved.metrics), y_true,
            np.asarray(values, dtype=float), race_ids)
        warnings.extend(w)
    timings["metric_seconds"] = t.seconds
    ok_metrics = tuple(
        name for name, payload in metric_payloads.items()
        if payload.get("status") == "OK")

    stage_labels = STAGES.stage_partition(val_frame["race_progress_frac"])
    with TIMING.Timer() as t:
        stage_payloads, w = RUN.evaluate_stages(
            prediction, ok_metrics, np.asarray(stage_labels), y_true,
            np.asarray(values, dtype=float), race_ids)
        warnings.extend(w)
    timings["stage_seconds"] = t.seconds

    with TIMING.Timer() as t:
        calibration_payload, w = RUN.evaluate_calibration(
            prediction, y_true, np.asarray(values, dtype=float))
        warnings.extend(w)
    timings["calibration_seconds"] = t.seconds

    holdout_races = tuple(sorted(set(str(r) for r in race_ids)))
    with TIMING.Timer() as t:
        race_payload, w = RUN.evaluate_winner_top_k(
            prediction, canonical, holdout_races,
            allow_protected_holdout=True)
        warnings.extend(w)
    timings["topk_seconds"] = t.seconds

    # measured inference performance (real samples only)
    with TIMING.Timer() as t:
        _, batch_samples = TIMING.timed_call(
            model.predict_positive_probability, X_holdout,
            repeats=BATCH_LATENCY_REPEATS, warmup=1)
        batch_summary = TIMING.latency_summary(batch_samples)
        n_states = int(X_holdout.shape[0])
        batch_summary["states_per_batch"] = n_states
        batch_summary["states_per_second"] = (
            n_states / batch_summary["mean"] if batch_summary["mean"] else None)
        single_frame = X_holdout.iloc[: min(SINGLE_STATE_SAMPLE, n_states)]

        def _single(row_index: int):
            return model.predict_positive_probability(
                single_frame.iloc[[row_index]])
        single_samples = []
        for row_index in range(len(single_frame)):
            _, samples = TIMING.timed_call(
                _single, row_index, repeats=1, warmup=0)
            single_samples.extend(samples)
        single_summary = TIMING.latency_summary(single_samples)
    timings["latency_probe_seconds"] = t.seconds

    prevalence = float(np.mean(np.asarray(dataset.y_train.astype(float))))

    # canonical evaluation-time total
    evaluation_seconds = (timings["metric_seconds"] + timings["stage_seconds"]
                          + timings["calibration_seconds"]
                          + timings["topk_seconds"])

    model_parameters = {
        **frozen_model_parameters(),
        "evaluation_split": SPLITS.HOLDOUT_ID,
        "final_fit_seasons": list(FINAL_FIT_SEASONS),
        "holdout_season": HOLDOUT_SEASON,
        "protocol_semantic_hash": protocol_semantic_hash(),
    }
    config = EX.build_config(
        M9_TASK, M9_FEATURE_SET, SPLITS.FINAL_FIT_ID,
        model_family=PROTECTED_EXPERIMENT_FAMILY, seed=M9_SEED,
        model_parameters=model_parameters,
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config={"method": "raw", "calibrated": False},
        training_rows=int(dataset.train_counts["eligible"]),
        training_races=int(dataset.train_metadata["race_id"].nunique()),
        validation_rows=int(dataset.validation_counts["eligible"]),
        validation_races=int(dataset.validation_metadata["race_id"].nunique()),
        holdout_accessed=True,
        holdout_purpose="M9 one-shot protected 2025 final evaluation",
    )

    result = EX.ExperimentResult(
        experiment_id=config.experiment_id,
        status=EX.ExperimentStatus.OK,
        fit_seconds=model.timing.get("estimator_fit_seconds"),
        prediction_seconds=timings["holdout_prediction_seconds"],
        latency={"batch": batch_summary, "single_state": single_summary,
                 "method": "batch: 1 warm-up + "
                 f"{BATCH_LATENCY_REPEATS} timed full-holdout predicts; "
                 "single-state: one timed predict per state over "
                 f"{len(single_frame)} states"},
        metrics={"train_prevalence": {"status": "INFO", "value": prevalence},
                 **metric_payloads},
        calibration=(calibration_payload
                     if calibration_payload.get("status") == "OK" else None),
        stage_metrics=stage_payloads,
        race_metrics={"winner_top_k": race_payload},
        artifact_refs={
            "model_family": PROTECTED_EXPERIMENT_FAMILY,
            "model_parameters": model_parameters,
            "preprocessing": PRE.preprocessing_contract_dict(),
            "sklearn_version": TC.SKLEARN_VERSION,
            "n_features_in": int(len(model._feature_names)),
            "transformed_dim": int(model.preprocessor.output_dim),
            "coefficient_sanity": model.sanity().get("coefficient_sanity"),
            "fit_warnings": list(model.fit_warnings),
            "peak_rss_bytes": _peak_rss_bytes(),
            "holdout_accessed": True,
            "evaluation_split": SPLITS.HOLDOUT_ID,
        },
        warnings=warnings,
        environment=RES.environment_metadata(
            paths.root if paths is not None else None),
    )
    dest = RES.write_experiment(config, result, paths=paths, root=root)

    log_loss_rm, per_race_ll = _race_macro(result, "log_loss")
    brier_rm, per_race_brier = _race_macro(result, "brier")

    race_order = (
        canonical.frame.loc[canonical.frame["season"].astype(int)
                            == HOLDOUT_SEASON, ["race_id", "round_no"]]
        .drop_duplicates().sort_values(["round_no", "race_id"]))
    race_meta = dataset.validation_metadata.copy()
    race_meta["race_id"] = race_meta["race_id"].astype(str)
    per_race = []
    for row in race_order.itertuples(index=False):
        race_id = str(row.race_id)
        n_states = int((race_meta["race_id"] == race_id).sum())
        sync = (race_payload.get("per_race", {}) or {}).get(race_id, {})
        accuracy = sync.get("accuracy", {}) or {}
        per_race.append({
            "race_id": race_id,
            "round": int(row.round_no),
            "eligible_states": n_states,
            "race_macro_log_loss": per_race_ll.get(race_id),
            "race_macro_brier": per_race_brier.get(race_id),
            "top1": accuracy.get("top1"),
            "top3": accuracy.get("top3"),
            "coverage_status": (
                "OK" if sync.get("n_evaluation_states", 0) > 0
                else "SKIPPED"),
            "n_skipped_no_predictions": sync.get(
                "n_skipped_no_predictions"),
            "n_skipped_winner_unobservable": sync.get(
                "n_skipped_winner_unobservable"),
            "n_skipped_degenerate": sync.get("n_skipped_degenerate"),
        })

    uncertainty: dict
    if bootstrap:
        uncertainty = {
            "race_macro_log_loss": race_macro_bootstrap(
                y_true, values, race_ids, "log_loss"),
            "race_macro_brier": race_macro_bootstrap(
                y_true, values, race_ids, "brier"),
        }
    else:
        uncertainty = {"status": "NOT_IMPLEMENTED", "reason": "disabled"}

    calibration = result.calibration or {}
    payload = {
        "result": result,
        "config": config,
        "dest": str(dest),
        "counts": counts,
        "predictions": np.asarray(values, dtype=float),
        "race_ids": race_ids,
        "y_true": y_true,
        "timings": timings,
        "evaluation_seconds": evaluation_seconds,
        "batch_summary": batch_summary,
        "single_summary": single_summary,
        "reliability": {
            "expected_calibration_error": calibration.get(
                "expected_calibration_error"),
            "brier": calibration.get("brier"),
            "n": calibration.get("n"),
            "n_bins": calibration.get("n_bins"),
            "binning": calibration.get("binning"),
            "bins": calibration.get("bins"),
        },
        "reliability_summary": _reliability_summary(calibration.get("bins")),
        "per_race": per_race,
        "race_macro_log_loss": log_loss_rm,
        "race_macro_brier": brier_rm,
        "topk": race_payload,
        "uncertainty": uncertainty,
        "warnings": warnings,
    }
    return payload


# --- development comparison ---------------------------------------------------


def _read_json(path) -> dict:
    return json.loads(Path(path).read_text())


def _mean(values) -> float | None:
    arr = [float(v) for v in values
           if v is not None and math.isfinite(float(v))]
    return float(np.mean(arr)) if arr else None


def development_comparison(holdout: dict, *, paths=None, root=None) -> dict:
    """Descriptive holdout-vs-development differences (no overfit claim)."""
    m7 = _read_json(m7_artifact_path(paths, root))
    m8 = _read_json(m8_artifact_path(paths, root))
    m7_agg = m7["aggregate"]
    raw = m8["aggregate"]["RAW"]

    primary = {
        "name": "M7 frozen-global outer development evaluation (D1/D2/D3)",
        "artifact": M7_ARTIFACT_FILENAME,
        "race_macro_log_loss": m7_agg["log_loss"]["mean"],
        "race_macro_brier": m7_agg["brier"]["mean"],
        "race_macro_roc_auc": m7_agg["roc_auc"]["mean"],
        "race_macro_pr_auc": m7_agg["pr_auc"]["mean"],
        "state_pooled_log_loss": m7_agg["state_pooled_log_loss"]["mean"],
        "state_pooled_brier": m7_agg["state_pooled_brier"]["mean"],
        "expected_calibration_error":
            m7_agg["expected_calibration_error"]["mean"],
        "winner_top1": m7_agg["winner_top_k"]["top1"]["mean"],
        "winner_top3": m7_agg["winner_top_k"]["top3"]["mean"],
        "training_design": (
            "Frozen global specification C=0.01, but each outer fold refit "
            "with its per-fold selected C (D1=0.003, D2=0.01, D3=0.03) on "
            "2018-(2021/2022/2023); three one-season-ahead validations."),
    }
    secondary = {
        "name": "M8 RAW calibration evaluation (base C=0.01; calibration "
                "season withheld from base fit)",
        "artifact": M8_ARTIFACT_FILENAME,
        "race_macro_log_loss": raw["race_macro_log_loss"]["mean"],
        "race_macro_brier": raw["race_macro_brier"]["mean"],
        "race_macro_roc_auc": raw["race_macro_roc_auc"]["mean"],
        "race_macro_pr_auc": raw["race_macro_pr_auc"]["mean"],
        "state_pooled_log_loss": raw["state_pooled_log_loss"]["mean"],
        "state_pooled_brier": raw["state_pooled_brier"]["mean"],
        "expected_calibration_error":
            raw["expected_calibration_error"]["mean"],
        "winner_top1": raw["winner_top1"]["mean"],
        "winner_top3": raw["winner_top3"]["mean"],
        "training_design": (
            "Base LogisticRegression C=0.01 fit on base seasons only (the "
            "last development-training season is a calibration season), so "
            "the base fit deliberately sees fewer rows than the M9 final "
            "fit; RAW outer metrics are therefore not directly equivalent "
            "to the final-fit development model."),
    }

    holdout_rm = {
        "race_macro_log_loss": holdout["race_macro_log_loss"],
        "race_macro_brier": holdout["race_macro_brier"],
        "race_macro_roc_auc": _race_macro(holdout["result"], "roc_auc")[0],
        "race_macro_pr_auc": _race_macro(holdout["result"], "pr_auc")[0],
        "state_pooled_log_loss":
            _state_pooled(holdout["result"], "log_loss"),
        "state_pooled_brier": _state_pooled(holdout["result"], "brier"),
        "expected_calibration_error":
            holdout["reliability"]["expected_calibration_error"],
        "winner_top1": (holdout["topk"].get("accuracy", {}) or {}).get("top1"),
        "winner_top3": (holdout["topk"].get("accuracy", {}) or {}).get("top3"),
    }

    def _delta(metric):
        ref = primary.get(metric)
        obs = holdout_rm.get(metric)
        if ref is None or obs is None:
            return None
        return float(obs - ref)

    differences = {metric: _delta(metric) for metric in (
        "race_macro_log_loss", "race_macro_brier", "race_macro_roc_auc",
        "race_macro_pr_auc", "state_pooled_log_loss", "state_pooled_brier",
        "expected_calibration_error", "winner_top1", "winner_top3")}

    # M8 RAW stage reference (mean across D1/D2/D3)
    stage_reference = {}
    for stage in ("EARLY", "MID", "LATE"):
        per_fold = m8.get("stage_metrics", {}).get(stage, {}).get("RAW", {})
        stage_reference[stage] = _mean(per_fold.values())

    holdout_stage = {}
    for stage in ("EARLY", "MID", "LATE"):
        node = (holdout["result"].stage_metrics or {}).get(
            "log_loss", {}).get(stage, {})
        holdout_stage[stage] = node.get("race_macro", {}).get("value")

    return {
        "primary_reference": primary,
        "secondary_reference": secondary,
        "holdout": holdout_rm,
        "differences_vs_primary": differences,
        "stage_log_loss": {
            "holdout": holdout_stage,
            "m8_raw_reference": stage_reference,
            "difference": {
                stage: (None if holdout_stage[stage] is None
                        or stage_reference[stage] is None
                        else float(holdout_stage[stage]
                                   - stage_reference[stage]))
                for stage in ("EARLY", "MID", "LATE")},
        },
        "interpretation": (
            "GENERALIZATION / HOLDOUT-DEVELOPMENT DIFFERENCES, descriptive "
            "only. Training design differs (single all-data fit predicting "
            "one season ahead vs multi-fold development evidence with "
            "less training data), so differences are not an overfitting "
            "diagnosis and carry no statistical certainty claim."),
    }


# --- artifact assembly --------------------------------------------------------


def _fresh_declaration(paths, root) -> dict:
    path = preunlock_path(paths, root)
    if not path.exists():
        raise ExperimentConfigError(
            f"pre-unlock declaration missing at {path}; the holdout must not "
            "be evaluated before it is written")
    declaration = _read_json(path)
    if declaration.get("holdout_target_metrics_evaluated_by_m9") is not False:
        raise ExperimentConfigError(
            "pre-unlock declaration does not state that 2025 target metrics "
            "were unevaluated; refusing to treat it as pre-unlock")
    if declaration.get("specification_fingerprint") \
            != specification_fingerprint():
        raise ExperimentConfigError(
            "pre-unlock declaration fingerprint does not match the frozen "
            "specification")
    return declaration


def assemble_holdout_artifact(holdout: dict, determinism: dict, *,
                              paths=None, root=None) -> dict:
    declaration = _fresh_declaration(paths, root)
    pre_path = preunlock_path(paths, root)
    result = holdout["result"]
    counts = holdout["counts"]
    immutability = immutability_report(paths, root)

    race_macro = {metric: _race_macro(result, metric)[0]
                  for metric in ("log_loss", "brier", "roc_auc", "pr_auc")}
    state_pooled = {metric: _state_pooled(result, metric)
                    for metric in ("log_loss", "brier", "roc_auc", "pr_auc")}
    topk = holdout["topk"]

    performance = {
        "preprocessing_fit_seconds": determinism["timings"][
            "preprocessing_fit_seconds"],
        "estimator_fit_seconds": determinism["timings"][
            "estimator_fit_seconds"],
        "transform_train_seconds": determinism["timings"][
            "transform_train_seconds"],
        "holdout_transform_seconds": holdout["timings"][
            "holdout_transform_seconds"],
        "holdout_prediction_seconds": holdout["timings"][
            "holdout_prediction_seconds"],
        "evaluation_seconds": holdout["evaluation_seconds"],
        "topk_seconds": holdout["timings"]["topk_seconds"],
        "batch_inference": holdout["batch_summary"],
        "single_state_latency": holdout["single_summary"],
        "peak_rss_bytes": _peak_rss_bytes(),
    }

    determinism_public = {
        key: determinism[key] for key in (
            "fixture", "fixture_states", "max_abs_probability_difference",
            "max_abs_preprocessed_difference",
            "max_abs_coefficient_difference", "identical_transformed_dim",
            "final_fit_counts")}

    model = determinism["model"]
    feature_names = list(model._feature_names)
    feature_names_hash = hashlib.sha256(
        "\n".join(feature_names).encode("utf-8")).hexdigest()
    model_fingerprint = _model_fingerprint(model)

    artifact = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "stage": "M9",
        "title": (
            "Final development fit + one-shot protected 2025 holdout "
            "evaluation"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "preunlock": {
            "path": str(pre_path),
            "sha256": _sha256_file(pre_path),
            "specification_fingerprint": declaration[
                "specification_fingerprint"],
            "holdout_target_metrics_evaluated_before_unlock": False,
        },
        "final_fit": {
            "specification": frozen_specification(),
            "specification_fingerprint": specification_fingerprint(),
            "model_parameters": frozen_model_parameters(),
            "preprocessing": PRE.preprocessing_contract_dict(),
            "counts": determinism["final_fit_counts"],
            "train_prevalence": float(np.mean(np.asarray(
                determinism["dataset"].y_train.astype(float)))),
            "feature_count": len(feature_names),
            "feature_names_ordered": feature_names,
            "feature_names_hash": feature_names_hash,
            "transformed_dim": int(model.preprocessor.output_dim),
            "sklearn_version": TC.SKLEARN_VERSION,
            "coefficient_sanity": model.sanity().get("coefficient_sanity"),
            "fit_warnings": list(model.fit_warnings),
            "model_fingerprint": model_fingerprint,
        },
        "holdout": {
            "season": HOLDOUT_SEASON,
            "counts": counts,
            "target": "is_winner",
            "eligibility_mask": "eligible_is_winner",
        },
        "holdout_access": {
            "explicit_opt_in": True,
            "materialization_access_count": 1,
            "target_evaluation_count": 1,
            "purpose": "M9 one-shot protected 2025 final evaluation",
            "firewall_preserved": (
                "ordinary development runners continue to reject HOLDOUT; "
                "only this sanctioned M9 evaluator passes "
                "allow_protected_holdout=True"),
        },
        "metrics": {
            "race_macro": race_macro,
            "state_pooled": state_pooled,
            "discrimination": {
                "roc_auc": race_macro["roc_auc"],
                "pr_auc": race_macro["pr_auc"],
            },
            "train_prevalence": float(np.mean(np.asarray(
                determinism["dataset"].y_train.astype(float)))),
        },
        "stages": result.stage_metrics,
        "reliability": holdout["reliability"],
        "reliability_summary": holdout["reliability_summary"],
        "synchronized": {
            "winner_top_k": topk,
            "metric_scope": (
                "top-k is computed by the frozen synchronized race adapter "
                "on INDEPENDENT_BINARY probabilities; it is not a "
                "categorical race distribution"),
        },
        "per_race": holdout["per_race"],
        "performance": performance,
        "determinism": determinism_public,
        "uncertainty": holdout["uncertainty"],
        "development_comparison": development_comparison(
            holdout, paths=paths, root=root),
        "protected_experiment": {
            "experiment_id": holdout["config"].experiment_id,
            "dest": holdout["dest"],
            "model_family": PROTECTED_EXPERIMENT_FAMILY,
            "fold": holdout["config"].fold,
            "evaluation_split": SPLITS.HOLDOUT_ID,
            "holdout_accessed": bool(holdout["config"].holdout_accessed),
            "C": FROZEN_C,
            "feature_set": M9_FEATURE_SET,
            "calibration_method": "RAW",
        },
        "hashes": immutability,
        "warnings": list(holdout["warnings"]),
        "probability_semantics_statement": (
            "The winner model emits independent per-driver binary "
            "probabilities (BINARY_PROBABILITY / INDEPENDENT_BINARY). They "
            "are NOT normalized to sum to 1 across a race and must not be "
            "treated as a categorical race distribution."),
        "limitations": [
            "Independent per-driver winner probabilities; no mutually "
            "exclusive race distribution.",
            "FastF1-era data/label limitations apply.",
            "Telemetry and reliability/DNF modelling remain deferred.",
            "Model performance varies by race stage.",
            "Development hyperparameter uncertainty is documented in M7.",
            "The protected holdout is a single season (24 races).",
            "No post-holdout tuning, calibration or model change occurred.",
        ],
        "no_post_holdout_tuning_statement": (
            "The frozen pipeline was evaluated exactly once on 2025 and no "
            "post-holdout tuning, calibration, thresholding, feature "
            "selection, model switching or ablation was performed."),
    }
    return _jsonable(artifact)


def _model_fingerprint(model) -> str:
    coef = np.asarray(model.estimator.coef_, dtype=float)
    intercept = np.asarray(model.estimator.intercept_, dtype=float)
    h = hashlib.sha256()
    h.update(coef.tobytes())
    h.update(intercept.tobytes())
    h.update("\n".join(model._feature_names).encode("utf-8"))
    return h.hexdigest()


def write_final_model_metadata(model, dataset, counts: dict, *,
                               holdout_artifact_name: str,
                               paths=None, root=None) -> Path:
    """Persist a metadata-only reproduction descriptor (no estimator blob).

    The Model Lab deliberately does not serialize fitted estimators: M0's
    STORAGE_POLICY keeps fitted model artifacts gitignored and no opaque
    pickle convention exists. This descriptor records everything needed to
    reproduce the exact fitted model.
    """
    dest = final_model_dir(paths, root)
    dest.mkdir(parents=True, exist_ok=True)
    feature_names = list(model._feature_names)
    metadata = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "stage": "M9",
        "final_model_name": FINAL_MODEL_NAME,
        "persistence": "metadata_only_no_estimator_serialization",
        "persistence_note": (
            "Fitted estimators are intentionally not serialized by the Model "
            "Lab; this descriptor is sufficient to reproduce the model from "
            "the frozen matrix and specification."),
        "specification": frozen_specification(),
        "specification_fingerprint": specification_fingerprint(),
        "model_parameters": frozen_model_parameters(),
        "preprocessing": PRE.preprocessing_contract_dict(),
        "feature_names_ordered": feature_names,
        "feature_names_hash": hashlib.sha256(
            "\n".join(feature_names).encode("utf-8")).hexdigest(),
        "transformed_dim": int(model.preprocessor.output_dim),
        "sklearn_version": TC.SKLEARN_VERSION,
        "training_seasons": list(FINAL_FIT_SEASONS),
        "training_counts": counts,
        "train_prevalence": float(np.mean(np.asarray(
            dataset.y_train.astype(float)))),
        "model_fingerprint": _model_fingerprint(model),
        "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "holdout_artifact": holdout_artifact_name,
        "creation_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return RES.atomic_write_json(dest / "metadata.json", metadata)


# --- M9 orchestration ---------------------------------------------------------


def run_m9(*, paths=None, root=None, allow_protected_holdout: bool = False,
           out=None, bootstrap: bool = True) -> dict:
    """Pre-unlock gate -> declaration -> final fit -> one-shot holdout.

    The protected 2025 holdout is accessed exactly once and only when
    ``allow_protected_holdout=True``.
    """
    if not allow_protected_holdout:
        raise ProtectedHoldoutError(
            "M9 requires the explicit protected-holdout opt-in "
            "(allow_protected_holdout=True)")
    _refuse_if_holdout_consumed(paths=paths, root=root, out=out)

    canonical = DATA.load_canonical(paths)
    if canonical.manifest.get("content_hash") != EXPECTED_MATRIX_CONTENT_HASH:
        from v2.model_lab.errors import ProtocolDriftError
        raise ProtocolDriftError("matrix content hash drift at M9 run time")

    # 1. Pre-unlock gate (no 2025 targets).
    gate = run_preunlock_gate(canonical, paths=paths, root=root)

    # 2. Immutable pre-unlock declaration BEFORE any 2025 access.
    if not preunlock_path(paths, root).exists():
        write_preunlock_declaration(canonical, paths=paths, root=root)
    declaration = _fresh_declaration(paths, root)

    # 3. Final fit + determinism on a development fixture.
    determinism = final_fit_determinism(canonical, paths=paths, root=root)

    # 4. ONE sanctioned 2025 target evaluation.
    holdout = evaluate_protected_holdout(
        determinism["model"], canonical, allow_protected_holdout=True,
        paths=paths, root=root, bootstrap=bootstrap)

    # 5. Artifacts.
    artifact = assemble_holdout_artifact(
        holdout, determinism, paths=paths, root=root)
    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, artifact)
    metadata_path = write_final_model_metadata(
        determinism["model"], determinism["dataset"],
        determinism["final_fit_counts"],
        holdout_artifact_name=FINAL_HOLDOUT_FILENAME, paths=paths, root=root)

    artifact["_summary_path"] = str(dest)
    artifact["_metadata_path"] = str(metadata_path)
    artifact["_gate"] = gate
    artifact["_declaration"] = declaration
    artifact["_holdout_counts"] = holdout["counts"]
    artifact["_dest"] = holdout["dest"]
    return artifact


# --- freeze manifest + deterministic document rendering -----------------------

#: Stage artifacts whose bytes must be unchanged by M9.
STAGE_ARTIFACT_FILES = {
    "M2_baseline_suite": "baseline_suite_v1.json",
    "M3_logreg_reference": "logreg_reference_v1.json",
    "M4_nonlinear_candidates": "nonlinear_candidates_v1.json",
    "M5_bagged_candidates": "bagged_candidates_v1.json",
    "M6_tuning_selection": "tuning_selection_v1.json",
    "M7_boundary_resolution": "logreg_boundary_resolution_v1.json",
    "M8_calibration_selection": "calibration_selection_v1.json",
}

MODEL_LAB_HISTORY: tuple = (
    ("M0", "Frozen experimental protocol: temporal folds D1/D2/D3, "
           "protected 2025 holdout, probability metrics, leakage rules."),
    ("M1", "Reusable experiment infrastructure (data, tasks, splits, "
           "predictions, metrics, calibration, aggregation, results)."),
    ("M1.1", "Prediction-semantics correctness guard (independent binary "
             "probabilities are never treated as race distributions)."),
    ("M2", "Non-ML baselines (CURRENT_LEADER/ORDER, GRID_POLE, RECENT_PACE, "
           "CLASS_PRIOR) on the canonical evaluation path."),
    ("M3", "Logistic Regression reference (LogReg C=1.0, ALL_84, train-fitted "
           "preprocessing)."),
    ("M4", "Boosted-tree candidates (HistGradientBoosting, XGBoost)."),
    ("M5", "Bagged-tree candidates (ExtraTrees, RandomForest)."),
    ("M6", "Nested chronological tuning of LogReg and ExtraTrees inside "
           "development folds."),
    ("M7", "Regularization boundary resolution and global deployment "
           "configuration freeze: Logistic Regression C=0.01."),
    ("M8", "Calibration evaluation (RAW / Platt / isotonic); RAW retained "
           "because calibrated alternatives did not clear the predeclared "
           "guards."),
    ("M9", "Final development fit on all eligible 2018-2024 rows + one-shot "
           "protected 2025 holdout evaluation; Model Lab freeze."),
)


def _fnum(value, digits: int = 6) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _stage_value(artifact: dict, stage: str) -> float | None:
    node = (artifact.get("stages") or {}).get("log_loss", {}).get(stage, {})
    return node.get("race_macro", {}).get("value")


def render_model_card(artifact: dict) -> str:
    """Deterministic model card rendered from the stored M9 artifact only."""
    spec = artifact["final_fit"]["specification"]
    params = artifact["final_fit"]["model_parameters"]
    counts = artifact["final_fit"]["counts"]
    hold = artifact["holdout"]["counts"]
    rm = artifact["metrics"]["race_macro"]
    sp = artifact["metrics"]["state_pooled"]
    rel = artifact["reliability"]
    topk = artifact["synchronized"]["winner_top_k"]
    acc = topk.get("accuracy", {})
    lines = [
        "# Model Lab Final Model Card",
        "",
        "## MODEL",
        "",
        "Logistic Regression "
        f"(`{params['estimator']}`, C={params['C']}).",
        "",
        "## TASK",
        "",
        "In-race winner binary probability: `is_winner` under "
        "`eligible_is_winner`.",
        "",
        "## DATA",
        "",
        "Rich FastF1 canonical driver-state matrix, 2018-2025.",
        f"- development / final fit: {spec['final_fit_seasons'][0]}-"
        f"{spec['final_fit_seasons'][-1]} "
        f"({counts['races']} races, {counts['eligible']} eligible states, "
        f"{counts['positives']} positives)",
        f"- protected holdout: {spec['holdout_season']} "
        f"({hold['races']} races, {hold['eligible']} eligible states, "
        f"{hold['positives']} positives)",
        "",
        "## FEATURES",
        "",
        "`ALL_84` temporally safe feature set "
        f"({artifact['final_fit']['feature_count']} predictive features; "
        "train-fitted median imputation + StandardScaler for numeric, "
        "most-frequent + float cast for boolean, constant `MISSING` + "
        "train-fitted one-hot for categorical).",
        "",
        "## MODEL SPEC",
        "",
        f"- estimator: `{params['estimator']}`",
        f"- C: {params['C']}",
        f"- solver: {params['solver']}",
        f"- max_iter: {params['max_iter']}",
        f"- class_weight: {params['class_weight']}",
        f"- random_state: {params['random_state']}",
        f"- penalty: {params['penalty']}",
        f"- project seed: {spec['seed']}",
        f"- fingerprint: `{artifact['final_fit']['specification_fingerprint']}`",
        "",
        "## CALIBRATION",
        "",
        "RAW selected because the M8 calibration alternatives (Platt, "
        "isotonic) did not improve development probability quality under the "
        "predeclared selection rule. No calibrator is fitted or applied.",
        "",
        "## PROBABILITY SEMANTICS",
        "",
        "Independent per-driver binary probability. The model does NOT "
        "output a mutually exclusive race distribution and its probabilities "
        "are not normalized to sum to 1 across a race. Synchronized top-k "
        "uses the frozen race adapter on these independent probabilities.",
        "",
        "## EVALUATION",
        "",
        "Development protocol: expanding-window chronological folds D1-D3 "
        "(M2-M8), headline race-macro aggregation.",
        f"One-shot protected {spec['holdout_season']} holdout "
        "(M9), first and only sanctioned target evaluation.",
        "",
        "## 2025 PROTECTED HOLDOUT (HEADLINE)",
        "",
        f"- race-macro log loss: {_fnum(rm['log_loss'])}",
        f"- race-macro Brier: {_fnum(rm['brier'])}",
        f"- state-pooled log loss: {_fnum(sp['log_loss'])}",
        f"- state-pooled Brier: {_fnum(sp['brier'])}",
        f"- ROC-AUC: {_fnum(rm['roc_auc'])}",
        f"- PR-AUC: {_fnum(rm['pr_auc'])}",
        f"- ECE (10 equal-width bins): {_fnum(rel['expected_calibration_error'])}",
        f"- synchronized top-1: {_fnum(acc.get('top1'), 4)}",
        f"- synchronized top-3: {_fnum(acc.get('top3'), 4)}",
        "",
        "## LIMITATIONS",
        "",
        "- independent winner probabilities, not a categorical race "
        "distribution;",
        "- FastF1-era data limitations;",
        "- two known Phase-1 partial sessions retained (not dropped);",
        "- telemetry modelling deferred;",
        "- reliability/DNF modelling deferred;",
        "- performance varies by race stage;",
        "- development hyperparameter uncertainty documented in M7;",
        "- the holdout is one season (24 races); no post-holdout tuning.",
        "",
    ]
    return "\n".join(lines)


def render_final_report(artifact: dict) -> str:
    """Deterministic Phase-3 Model Lab culmination report."""
    spec = artifact["final_fit"]["specification"]
    params = artifact["final_fit"]["model_parameters"]
    counts = artifact["final_fit"]["counts"]
    hold = artifact["holdout"]["counts"]
    rm = artifact["metrics"]["race_macro"]
    sp = artifact["metrics"]["state_pooled"]
    rel = artifact["reliability"]
    topk = artifact["synchronized"]["winner_top_k"]
    acc = topk.get("accuracy", {})
    dc = artifact["development_comparison"]
    primary = dc["primary_reference"]
    secondary = dc["secondary_reference"]
    perf = artifact["performance"]

    lines = [
        "# Model Lab Final Report",
        "",
        "Phase 3 (Model Lab) culmination: M0-M9.",
        "",
        "## Stage history",
        "",
    ]
    for stage, summary in MODEL_LAB_HISTORY:
        lines.append(f"- **{stage}** - {summary}")
    lines += [
        "",
        "## What was tried and rejected",
        "",
        "- M2 factual baselines were sanity references, not candidates.",
        "- M3 LogReg C=1.0 was a reference, not the final configuration.",
        "- M4 boosted trees and M5 bagged trees (ExtraTrees/RandomForest) "
        "were rejected in favour of the simpler linear model on probability "
        "quality and operational cost.",
        "- M6 nested chronological tuning selected candidates but did not "
        "justify a tree model over LogReg.",
        "- M7 resolved the regularization boundary and froze C=0.01.",
        "- M8 rejected Platt and isotonic calibration; RAW was retained "
        "because the calibrated alternatives did not clear the predeclared "
        "guards.",
        "",
        "## Why Logistic Regression, C=0.01, RAW",
        "",
        "- LogReg gave competitive development probability quality at the "
        "lowest complexity/cost class (M4/M5/M6 comparisons).",
        "- C=0.01 was the M7 global development-only freeze rule outcome "
        "(aggregate inner log-loss fallback; no strict per-fold majority).",
        "- RAW won the M8 predeclared calibration-selection rule; no "
        "calibration layer was justified.",
        "",
        "## Development evidence (frozen references)",
        "",
        f"- M7 frozen-global outer (D1/D2/D3): "
        f"race-macro log loss {_fnum(primary['race_macro_log_loss'])}, "
        f"Brier {_fnum(primary['race_macro_brier'])}, "
        f"ROC-AUC {_fnum(primary['race_macro_roc_auc'])}, "
        f"PR-AUC {_fnum(primary['race_macro_pr_auc'])}, "
        f"top-1 {_fnum(primary['winner_top1'], 4)}.",
        f"- M8 RAW (base C=0.01, calibration season withheld): "
        f"race-macro log loss {_fnum(secondary['race_macro_log_loss'])}, "
        f"Brier {_fnum(secondary['race_macro_brier'])}, "
        f"ROC-AUC {_fnum(secondary['race_macro_roc_auc'])}, "
        f"PR-AUC {_fnum(secondary['race_macro_pr_auc'])}, "
        f"top-1 {_fnum(secondary['winner_top1'], 4)}.",
        "",
        "## Protected 2025 holdout (one-shot)",
        "",
        f"FINAL_FIT: {spec['final_fit_seasons'][0]}-"
        f"{spec['final_fit_seasons'][-1]} ({counts['races']} races, "
        f"{counts['eligible']} eligible states).",
        f"HOLDOUT: {spec['holdout_season']} ({hold['races']} races, "
        f"{hold['eligible']} eligible states).",
        "",
        f"- race-macro log loss: {_fnum(rm['log_loss'])}",
        f"- race-macro Brier: {_fnum(rm['brier'])}",
        f"- state-pooled log loss: {_fnum(sp['log_loss'])}",
        f"- state-pooled Brier: {_fnum(sp['brier'])}",
        f"- ROC-AUC: {_fnum(rm['roc_auc'])}",
        f"- PR-AUC: {_fnum(rm['pr_auc'])}",
        f"- ECE: {_fnum(rel['expected_calibration_error'])}",
        f"- synchronized top-1: {_fnum(acc.get('top1'), 4)}",
        f"- synchronized top-3: {_fnum(acc.get('top3'), 4)}",
        "",
        "## Stage breakdown (race-macro log loss)",
        "",
        f"- EARLY: {_fnum(_stage_value(artifact, 'EARLY'))}",
        f"- MID: {_fnum(_stage_value(artifact, 'MID'))}",
        f"- LATE: {_fnum(_stage_value(artifact, 'LATE'))}",
        "",
        "## Holdout-development differences (descriptive)",
        "",
    ]
    for metric, value in dc["differences_vs_primary"].items():
        lines.append(f"- {metric}: {_fnum(value)} (holdout minus M7)")
    lines += [
        "",
        dc["interpretation"],
        "",
        "## Latency and memory (measured)",
        "",
        f"- final preprocessing fit: "
        f"{_fnum(perf['preprocessing_fit_seconds'], 4)} s",
        f"- final model fit: {_fnum(perf['estimator_fit_seconds'], 4)} s",
        f"- holdout transform: "
        f"{_fnum(perf['holdout_transform_seconds'], 4)} s",
        f"- holdout prediction: "
        f"{_fnum(perf['holdout_prediction_seconds'], 4)} s",
        f"- canonical evaluation: "
        f"{_fnum(perf['evaluation_seconds'], 4)} s",
        f"- batch throughput: "
        f"{_fnum(perf['batch_inference'].get('states_per_second'), 2)} "
        "states/s",
        f"- single-state latency (mean): "
        f"{_fnum(perf['single_state_latency'].get('mean'), 6)} s",
        f"- peak RSS: {perf['peak_rss_bytes']} bytes",
        "",
        "## Leakage protections",
        "",
        "- 2025 was protected throughout M0-M8 and unlocked exactly once in "
        "M9 with explicit opt-in;",
        "- preprocessing is fit on FINAL_FIT training rows only;",
        "- the frozen mask defines eligibility; labels/masks never enter the "
        "design matrix;",
        "- metrics/preprocessing/feature ordering come from frozen Phase-2/M0 "
        "artifacts, never re-derived.",
        "",
        "## Probability semantics",
        "",
        artifact["probability_semantics_statement"],
        "",
        "## Reproducibility",
        "",
        f"- specification fingerprint: "
        f"`{artifact['final_fit']['specification_fingerprint']}`",
        f"- model fingerprint: "
        f"`{artifact['final_fit']['model_fingerprint']}`",
        f"- matrix content hash: "
        f"`{artifact['hashes']['phase2_matrix_content_hash']}`",
        f"- protocol semantic hash: "
        f"`{artifact['hashes']['m0_protocol_semantic_hash']}`",
        f"- protected experiment id: "
        f"`{artifact['protected_experiment']['experiment_id']}`",
        "",
        "## Final model specification",
        "",
        f"LogisticRegression, C={params['C']}, solver={params['solver']}, "
        f"max_iter={params['max_iter']}, class_weight={params['class_weight']}, "
        f"random_state={params['random_state']}; feature set "
        f"{spec['feature_set']}; train-fitted preprocessing; calibration RAW; "
        "independent binary probability semantics.",
        "",
        "## Limitations",
        "",
    ]
    for item in artifact["limitations"]:
        lines.append(f"- {item}")
    lines += [
        "",
        artifact["no_post_holdout_tuning_statement"],
        "",
    ]
    return "\n".join(lines)


def build_freeze_manifest(artifact: dict, *, paths=None, root=None,
                          test_results: dict | None = None) -> dict:
    """Final Model Lab freeze manifest (Phase-3)."""
    base = _base_dir(paths, root)
    stage_fingerprints = {}
    for name, filename in STAGE_ARTIFACT_FILES.items():
        path = reports_dir(paths, root) / filename
        stage_fingerprints[name] = {
            "path": filename,
            "sha256": _sha256_file(path) if path.exists() else None,
        }
    docs = {}
    for rel in (MODEL_CARD_REL, FINAL_REPORT_REL):
        path = base / rel
        docs[rel] = _sha256_file(path) if path.exists() else None
    manifest = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "model_lab_status": "FROZEN",
        "model_lab_phase": "3",
        "freeze_timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "phase2_frozen_hashes": artifact["hashes"],
        "stage_artifacts": stage_fingerprints,
        "final_model_specification": artifact["final_fit"]["specification"],
        "final_model_specification_fingerprint": artifact["final_fit"][
            "specification_fingerprint"],
        "final_model_fingerprint": artifact["final_fit"]["model_fingerprint"],
        "preunlock_fingerprint": artifact["preunlock"][
            "specification_fingerprint"],
        "preunlock_artifact_sha256": artifact["preunlock"]["sha256"],
        "holdout_artifact": {
            "path": FINAL_HOLDOUT_FILENAME,
            "sha256": _sha256_file(default_out(paths, root))
            if default_out(paths, root).exists() else None,
        },
        "final_model_artifact": {
            "path": f"{FINAL_MODEL_DIR_REL}/{FINAL_MODEL_NAME}/metadata.json",
            "sha256": None,
            "persistence": "metadata_only_no_estimator_serialization",
        },
        "documents": docs,
        "holdout_access_statement": (
            "2025 was unlocked exactly once by the sanctioned M9 evaluator "
            "with explicit opt-in; the result was used for reporting only."),
        "tests": test_results or {"status": "PENDING"},
        "known_xfails": [
            "Pre-Phase2 legacy Monaco-2022 NaN label defects remain "
            "documented expected xfails (unchanged by M9).",
        ],
        "known_limitations": artifact["limitations"],
    }
    meta_path = base / manifest["final_model_artifact"]["path"]
    if meta_path.exists():
        manifest["final_model_artifact"]["sha256"] = _sha256_file(meta_path)
    return manifest


def write_documents(artifact: dict, *, paths=None, root=None,
                    test_results: dict | None = None) -> dict:
    """Write the tracked model card, final report and freeze manifest."""
    base = _base_dir(paths, root)
    card = base / MODEL_CARD_REL
    report = base / FINAL_REPORT_REL
    manifest_path = base / FREEZE_MANIFEST_OUT_REL
    RES.atomic_write_text(card, render_model_card(artifact))
    RES.atomic_write_text(report, render_final_report(artifact))
    manifest = build_freeze_manifest(
        artifact, paths=paths, root=root, test_results=test_results)
    RES.atomic_write_json(manifest_path, manifest)
    return {"model_card": str(card), "final_report": str(report),
            "freeze_manifest": str(manifest_path), "manifest": manifest}


