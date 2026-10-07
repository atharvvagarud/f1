"""V3.3B controlled screening harness + OOF infrastructure (multi-model lab).

Thin extension over frozen Model Lab machinery; no science redefined:

- 110-column materialization: reuses
  ``v3_dynamics_experiment.load_joined_frame`` / ``v3_feature_names`` /
  ``materialize_v3`` (ALL_84 + CORE_26, state_id 1:1 join, M0 audit).
- Metrics/aggregation/stages/calibration/top-k: reused via
  ``runner.evaluate_*`` + ``aggregation`` (race-macro headline).
- Inner folds: reuses ``inner_splits.resolve_inner_splits`` (M6 nested
  temporal design); selection objective is mean inner race-macro log loss
  with the frozen 1e-6 simpler-wins tie rule.
- Comparison: reuses ``v3_dynamics_experiment.paired_bootstrap``
  (paired race resampling, seed 42, B=2000, 95% percentile CI).
- Firewall: development-only resolvers; HOLDOUT/2025/FINAL_FIT raise.

New in B (and only this): declarative 4-family candidate registry,
family-specific deterministic pipelines, preregistered grids (<=12),
canonical OOF schema + IO, provenance envelope, determinism and
serialization checks. Full four-family screening belongs to V3.3C;
B runs a labelled HARNESS_SMOKE_ONLY subset.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import inner_splits as INNER
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab import tasks as TASKS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutError,
)

#: Frozen V3.3A contract identity (Part A/C gate).
A_CONTRACT_SHA = "d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7"
A_CONTRACT_SCHEMA = "v3.3a-experiment-contract-v1"
A_CONTRACT_PATH = Path("results/v3/v3_3a/experiment_contract.json")

#: B preregistration identity.
B_PREREG_SCHEMA = "v3.3b-preregistration-v1"
B_PREREG_PATH = Path("results/v3/v3_3b/preregistration.json")

#: Frozen task / feature-arm identities.
TASK = "winner"
ARM_PRIMARY = "ALL_84_PLUS_V3_1_DYNAMICS_CORE"
ARM_CONTROL = "ALL_84"
N_84, N_CORE, N_110 = 84, 26, 110

#: Frozen development outer folds (D1/D2/D3); 2025 sealed.
OUTER_FOLDS = ("D1", "D2", "D3")
SEED = 42
TIE_TOLERANCE = 1e-6
BOOTSTRAP_SEED = 42
BOOTSTRAP_REPLICATES = 2000
THREAD_POLICY = {"n_jobs": 4, "note": "CPU only, M4, n_jobs<=4"}

#: Frozen V3.1B logistic control (harness must reproduce it exactly).
FROZEN_LOGR_C = 0.01

#: OOF parquet location (ignored data path; never committed).
OOF_DIR = Path("data/v3/v3_3b")

#: Canonical V3.3 OOF columns (Part O).
OOF_COLUMNS = (
    "state_id", "season", "race_id", "driver_id", "target", "fold",
    "stage", "feature_arm", "model_family", "model_config_id",
    "probability",
)

# ---------------------------------------------------------------------------
# Contract / preregistration verification
# ---------------------------------------------------------------------------

def _file_hash_hex(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def verify_a_contract() -> dict:
    """Fail closed unless the frozen V3.3A contract hash is exact."""
    contract = json.loads(A_CONTRACT_PATH.read_text())
    payload = {k: v for k, v in contract.items() if k != "contract_hash"}
    actual = _file_hash_hex(payload)
    if actual != A_CONTRACT_SHA:
        raise ExperimentConfigError(
            f"V3.3A contract hash mismatch: {actual} != {A_CONTRACT_SHA}")
    if contract.get("schema_version") != A_CONTRACT_SCHEMA:
        raise ExperimentConfigError("V3.3A contract schema drift")
    return {"contract_sha": actual,
            "schema_version": contract["schema_version"]}


def load_prereg() -> dict:
    if not B_PREREG_PATH.exists():
        raise ExperimentConfigError(
            f"B preregistration missing at {B_PREREG_PATH}; "
            "run scripts/freeze_v3_3b_prereg.py first")
    return json.loads(B_PREREG_PATH.read_text())


def verify_prereg() -> dict:
    """Fail closed unless the B preregistration hash is self-consistent."""
    prereg = load_prereg()
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    actual = _file_hash_hex(payload)
    if actual != prereg.get("preregistration_identity"):
        raise ExperimentConfigError("B preregistration hash mismatch")
    return {"prereg_sha": actual,
            "schema_version": prereg.get("schema_version")}


def verify_contracts() -> dict:
    """Verify A contract + B preregistration (every B script calls this)."""
    a = verify_a_contract()
    b = verify_prereg()
    return {"contract_sha": a["contract_sha"],
            "a_schema_version": a["schema_version"],
            "prereg_sha": b["prereg_sha"],
            "b_schema_version": b["schema_version"]}

# ---------------------------------------------------------------------------
# Candidate registry (Part G; exactly the four A-admitted families)
# ---------------------------------------------------------------------------

def candidate_registry() -> dict:
    """Declarative registry: no experimental results inside."""
    import sklearn

    import xgboost
    return {
        "logistic_regression": {
            "family_id": "logistic_regression",
            "implementation": "sklearn.linear_model.LogisticRegression",
            "implementation_version": sklearn.__version__,
            "pipeline_factory": "v3_3b_harness.build_estimator:logistic_regression",
            "parameter_namespace": ["C"],
            "fixed_parameters": dict(TC.LOGREG_FIXED),
            "seed_policy": "random_state=42",
            "thread_policy": "single-threaded lbfgs (n/a); pipeline n_jobs<=4",
            "missing_value_policy": "frozen TRAIN-only median/mode imputation",
            "scaling_policy": "frozen TRAIN-only StandardScaler (numerics)",
            "probability_interface": "predict_proba positive-class column; "
                                     "RAW INDEPENDENT_BINARY, never normalized",
            "serialization_type": "joblib (estimator, preprocessor, config)",
        },
        "hist_gradient_boosting": {
            "family_id": "hist_gradient_boosting",
            "implementation": "sklearn.ensemble.HistGradientBoostingClassifier",
            "implementation_version": sklearn.__version__,
            "pipeline_factory": "v3_3b_harness.build_estimator:hist_gradient_boosting",
            "parameter_namespace": ["learning_rate", "max_leaf_nodes",
                                    "min_samples_leaf"],
            "fixed_parameters": {
                "loss": "log_loss", "max_iter": 200,
                "max_depth": None, "l2_regularization": 0.0,
                "early_stopping": False, "random_state": 42,
            },
            "seed_policy": "random_state=42",
            "thread_policy": "OpenMP default; pipeline n_jobs<=4",
            "missing_value_policy": "frozen TRAIN-only median/mode imputation "
                                    "(native NaN support unused: identical "
                                    "pipeline keeps arms comparable)",
            "scaling_policy": "frozen TRAIN-only StandardScaler (neutral for "
                              "trees; identical pipeline)",
            "probability_interface": "predict_proba positive-class column; "
                                     "RAW INDEPENDENT_BINARY, never normalized",
            "serialization_type": "joblib (estimator, preprocessor, config)",
            "early_stopping_policy": "disabled (early_stopping=False); "
                                     "validation-driven training is leakage",
        },
        "extra_trees": {
            "family_id": "extra_trees",
            "implementation": "sklearn.ensemble.ExtraTreesClassifier",
            "implementation_version": sklearn.__version__,
            "pipeline_factory": "v3_3b_harness.build_estimator:extra_trees",
            "parameter_namespace": ["max_features", "min_samples_leaf",
                                    "max_depth"],
            "fixed_parameters": {k: v for k, v in TC.EXTRA_TREES_FIXED.items()},
            "seed_policy": "random_state=42",
            "thread_policy": "n_jobs=4",
            "missing_value_policy": "frozen TRAIN-only median/mode imputation",
            "scaling_policy": "frozen TRAIN-only StandardScaler (neutral for "
                              "trees; identical pipeline)",
            "probability_interface": "predict_proba positive-class column; "
                                     "RAW INDEPENDENT_BINARY, never normalized",
            "serialization_type": "joblib (estimator, preprocessor, config)",
        },
        "xgboost": {
            "family_id": "xgboost",
            "implementation": "xgboost.XGBClassifier",
            "implementation_version": xgboost.__version__,
            "pipeline_factory": "v3_3b_harness.build_estimator:xgboost",
            "parameter_namespace": ["learning_rate", "max_depth",
                                    "min_child_weight"],
            "fixed_parameters": {
                "objective": "binary:logistic", "eval_metric": "logloss",
                "n_estimators": 300, "subsample": 0.8,
                "colsample_bytree": 0.8, "reg_alpha": 0.0, "reg_lambda": 1.0,
                "tree_method": "hist", "n_jobs": 4, "random_state": 42,
            },
            "seed_policy": "random_state=42",
            "thread_policy": "n_jobs=4, tree_method=hist (CPU, M4)",
            "missing_value_policy": "frozen TRAIN-only median/mode imputation "
                                    "(native missing support unused: identical "
                                    "pipeline keeps arms comparable)",
            "scaling_policy": "frozen TRAIN-only StandardScaler (neutral for "
                              "trees; identical pipeline)",
            "probability_interface": "predict_proba positive-class column; "
                                     "RAW INDEPENDENT_BINARY, never normalized",
            "serialization_type": "joblib (estimator, preprocessor, config)",
            "early_stopping_policy": "no early stopping; no external "
                                     "validation/2025 for stopping",
        },
    }


def _require_family(family: str) -> dict:
    registry = candidate_registry()
    if family not in registry:
        raise ExperimentConfigError(
            f"unknown candidate family {family!r}; "
            f"admitted: {sorted(registry)}")
    return registry[family]

# ---------------------------------------------------------------------------
# Family-specific deterministic pipelines (Parts H-K)
# ---------------------------------------------------------------------------

def build_estimator(family: str, config: dict):
    """Fresh unfitted estimator for one family + preregistered config."""
    _require_family(family)
    if family == "logistic_regression":
        if set(config) != {"C"}:
            raise ExperimentConfigError(
                f"logistic_regression namespace is {{'C'}}; got {sorted(config)}")
        return TC.build_estimator(family, {"C": config["C"]})
    if family == "extra_trees":
        if set(config) != {"max_features", "min_samples_leaf", "max_depth"}:
            raise ExperimentConfigError(
                f"extra_trees namespace drift: {sorted(config)}")
        return TC.build_estimator(family, dict(config))
    if family == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingClassifier
        if set(config) != {"learning_rate", "max_leaf_nodes",
                           "min_samples_leaf"}:
            raise ExperimentConfigError(
                f"hist_gradient_boosting namespace drift: {sorted(config)}")
        return HistGradientBoostingClassifier(
            loss="log_loss", learning_rate=config["learning_rate"],
            max_iter=200, max_leaf_nodes=config["max_leaf_nodes"],
            max_depth=None, min_samples_leaf=config["min_samples_leaf"],
            l2_regularization=0.0, early_stopping=False, random_state=SEED)
    if family == "xgboost":
        from xgboost import XGBClassifier
        allowed = {"learning_rate", "max_depth", "min_child_weight",
                   "n_estimators"}
        if set(config) - allowed or not {"learning_rate", "max_depth",
                                         "min_child_weight"} <= set(config):
            raise ExperimentConfigError(
                f"xgboost namespace drift: {sorted(config)}")
        return XGBClassifier(
            objective="binary:logistic", eval_metric="logloss",
            n_estimators=int(config.get("n_estimators", 300)),
            learning_rate=config["learning_rate"],
            max_depth=config["max_depth"],
            min_child_weight=config["min_child_weight"],
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.0,
            reg_lambda=1.0, tree_method="hist", n_jobs=4,
            random_state=SEED)
    raise ExperimentConfigError(f"unknown candidate family {family!r}")


def resolved_parameters(family: str, config: dict) -> dict:
    """Full recorded parameter mapping (fixed + searched)."""
    _require_family(family)
    if family in ("logistic_regression", "extra_trees"):
        return TC.resolved_model_parameters(family, dict(config))
    if family == "hist_gradient_boosting":
        return {"estimator": "HistGradientBoostingClassifier",
                **candidate_registry()[family]["fixed_parameters"],
                **dict(config)}
    if family == "xgboost":
        out = {"estimator": "XGBClassifier",
               **candidate_registry()[family]["fixed_parameters"],
               **{k: v for k, v in config.items()
                  if k in ("learning_rate", "max_depth",
                           "min_child_weight")}}
        if config.get("n_estimators", 300) != 300:
            out["n_estimators"] = int(config["n_estimators"])
        return out
    return {"estimator": "XGBClassifier",
            **candidate_registry()[family]["fixed_parameters"],
            **dict(config)}

# ---------------------------------------------------------------------------
# Preregistered grids (Part L; compact, <=12, frozen before results)
# ---------------------------------------------------------------------------

def candidate_grids() -> dict:
    """Small scientifically-justified grids; logistic includes frozen C=0.01."""
    return {
        "logistic_regression": [
            {"C": 0.003},
            {"C": 0.01},
            {"C": 0.03},
            {"C": 0.1},
        ],
        "hist_gradient_boosting": [
            {"learning_rate": lr, "max_leaf_nodes": leaves,
             "min_samples_leaf": msl}
            for lr in (0.05, 0.1)
            for leaves in (15, 31)
            for msl in (20, 100)
        ],
        "extra_trees": [
            {"max_features": mf, "min_samples_leaf": msl,
             "max_depth": md}
            for mf in ("sqrt", 0.5)
            for msl in (1, 5)
            for md in (None, 20)
        ],
        "xgboost": [
            {"learning_rate": lr, "max_depth": depth,
             "min_child_weight": mcw}
            for lr in (0.05, 0.1)
            for depth in (3, 5)
            for mcw in (1, 5)
        ],
    }


def config_id(family: str, config: dict) -> str:
    """Deterministic human-readable configuration id."""
    _require_family(family)
    if family == "logistic_regression":
        return f"C={config['C']:g}"
    if family == "hist_gradient_boosting":
        return (f"lr={config['learning_rate']:g};"
                f"leaves={config['max_leaf_nodes']};"
                f"min_leaf={config['min_samples_leaf']}")
    if family == "extra_trees":
        depth = "None" if config["max_depth"] is None else str(
            config["max_depth"])
        return (f"max_features={config['max_features']};"
                f"min_samples_leaf={config['min_samples_leaf']};"
                f"max_depth={depth}")
    depth = str(config["max_depth"])
    base = (f"lr={config['learning_rate']:g};max_depth={depth};"
            f"min_child_weight={config['min_child_weight']}")
    if config.get("n_estimators", 300) != 300:
        base += f";n_estimators={int(config['n_estimators'])}"
    return base


def complexity_rank(family: str, config: dict) -> tuple:
    """Simpler/more-regularized sorts first (tie-break, frozen pre-results)."""
    _require_family(family)
    if family == "logistic_regression":
        return (config["C"],)
    if family == "hist_gradient_boosting":
        return (-int(config["min_samples_leaf"]),
                -int(config["max_leaf_nodes"]),
                config["learning_rate"])
    if family == "extra_trees":
        return (-int(config["min_samples_leaf"]),
                0 if config["max_depth"] is not None else 1,
                0 if config["max_features"] == "sqrt" else 1)
    return (-int(config["min_child_weight"]),
            int(config["max_depth"]), config["learning_rate"],
            int(config.get("n_estimators", 300)))

# ---------------------------------------------------------------------------
# Firewall (Part S)
# ---------------------------------------------------------------------------

def assert_development_fold(fold_id: str) -> None:
    """Only D1/D2/D3 may run; HOLDOUT/2025/FINAL_FIT raise fail-closed."""
    if fold_id in OUTER_FOLDS:
        return
    if fold_id in ("HOLDOUT", "2025", "HOLDOUT_2025",
                   str(SPLITS.HOLDOUT_ID)) or fold_id == SPLITS.FINAL_FIT_ID:
        raise ProtectedHoldoutError(
            f"V3.3B refuses {fold_id!r}: development folds "
            f"{list(OUTER_FOLDS)} only; 2025 holdout is sealed")
    V3C.assert_no_holdout_request(fold_id)


def assert_no_2025_in_frame(frame: pd.DataFrame, label: str) -> None:
    seasons = set(int(s) for s in frame["season"].astype(int).unique())
    if 2025 in seasons:
        raise ProtectedHoldoutError(f"{label}: 2025 rows reached B harness")

# ---------------------------------------------------------------------------
# Feature materialization helpers (Parts D-F; delegate to frozen V3.1C code)
# ---------------------------------------------------------------------------

def feature_names_110(names_84: tuple | None = None) -> tuple:
    """ALL_84 (frozen order) + CORE_26 (frozen order) = 110."""
    names = V3C.v3_feature_names(V3C.ARM_B, names_84)
    if len(names) != N_110:
        raise ExperimentConfigError(f"110-arm has {len(names)} columns")
    if len(names[:N_84]) != N_84 or len(names[N_84:]) != N_CORE:
        raise ExperimentConfigError("110-arm block structure drift")
    return names


def check_feature_contract(names_84: tuple, names_110: tuple) -> dict:
    """84 + 26 = 110; no 29-column sidecar leakage; no overlap."""
    from raceintel.features.dynamics import contract as DYN

    core = tuple(DYN.feature_set_names("core"))
    sidecar_all = tuple(DYN.feature_set_names("all"))
    if len(names_84) != N_84 or len(core) != N_CORE or \
            len(names_110) != N_110:
        raise ExperimentConfigError("feature counts drift (84/26/110)")
    if tuple(names_110[:N_84]) != tuple(names_84):
        raise ExperimentConfigError("110 prefix != ALL_84 order")
    if tuple(names_110[N_84:]) != core:
        raise ExperimentConfigError("110 suffix != CORE_26 order")
    if set(names_84) & set(core):
        raise ExperimentConfigError("ALL_84 overlaps CORE_26")
    non_core = [c for c in sidecar_all if c not in set(core)]
    leaked = [c for c in non_core if c in set(names_110)]
    if leaked:
        raise ExperimentConfigError(
            f"sidecar non-CORE columns leaked: {leaked}")
    if len(set(names_110)) != N_110:
        raise ExperimentConfigError("duplicate columns in 110-arm")
    return {
        "n_84": N_84, "n_core": N_CORE, "n_110": N_110,
        "sidecar_logical": len(sidecar_all),
        "sidecar_non_core_excluded": len(non_core),
        "feature_hash": hashlib.sha256(
            "\n".join(names_110).encode()).hexdigest(),
    }

# ---------------------------------------------------------------------------
# Generic fit / predict (TRAIN-only preprocessing, RAW probabilities)
# ---------------------------------------------------------------------------

def fit_family(X_train: pd.DataFrame, y_train: pd.Series,
               schema: DATA.FeatureSchema, family: str,
               config: dict) -> tuple:
    """Fit frozen TRAIN-only preprocessing + family estimator."""
    target = np.asarray(y_train.astype(float)).ravel()
    if set(np.unique(target)) - {0.0, 1.0}:
        raise ExperimentConfigError("winner target must be binary 0/1")
    with TIMING.Timer() as t:
        fitted = PRE.fit_preprocessor(X_train, schema)
    prep_s = t.seconds
    with TIMING.Timer() as t:
        train_matrix = fitted.transform(X_train)
    tr_s = t.seconds
    estimator = build_estimator(family, config)
    caught: list = []
    with TIMING.Timer() as t:
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            estimator.fit(train_matrix, target)
            for item in seen:
                caught.append(f"{item.category.__name__}: {item.message}")
    fit_s = t.seconds
    classes = list(estimator.classes_)
    if 1 not in classes:
        raise InvalidPredictionError(
            f"estimator classes {classes} lack positive class 1")
    info = {"preprocessing_fit_seconds": prep_s,
            "transform_train_seconds": tr_s,
            "estimator_fit_seconds": fit_s,
            "convergence_warnings": caught,
            "transformed_dim": int(fitted.output_dim),
            "positive_index": int(classes.index(1))}
    return fitted, estimator, info


def predict_family(fitted: PRE.FittedPreprocessor, estimator,
                   X_val: pd.DataFrame, state_ids: list) -> PR.PredictionResult:
    """RAW positive-class probabilities as typed INDEPENDENT_BINARY."""
    matrix = fitted.transform(X_val)
    if not np.all(np.isfinite(matrix)):
        raise InvalidPredictionError("transformed matrix contains NaN/inf")
    proba = np.asarray(
        estimator.predict_proba(matrix))[:, _positive_index(estimator)]
    if not np.all(np.isfinite(proba)):
        raise InvalidPredictionError("non-finite candidate probabilities")
    if np.any((proba < 0.0) | (proba > 1.0)):
        raise InvalidPredictionError("candidate probabilities outside [0, 1]")
    return PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(state_ids),
        values=np.asarray(proba, dtype=float),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY,
        positive_class=1)


def _positive_index(estimator) -> int:
    return int(list(estimator.classes_).index(1))

# ---------------------------------------------------------------------------
# Outer-fold evaluation (Part N; mirrors run_v3_arm evaluation chain)
# ---------------------------------------------------------------------------

def run_outer(augmented: DATA.CanonicalMatrix,
              plain: DATA.CanonicalMatrix, fold_id: str, family: str,
              config: dict, feature_arm: str = ARM_PRIMARY,
              feature_names: tuple | None = None) -> dict:
    """Fit selected config on outer TRAIN; predict outer validation once."""
    verify_contracts()
    assert_development_fold(fold_id)
    _require_family(family)
    if feature_arm not in (ARM_PRIMARY, ARM_CONTROL):
        raise ExperimentConfigError(
            f"unknown B feature arm {feature_arm!r}")
    if feature_names is None:
        feature_names = (feature_names_110() if feature_arm == ARM_PRIMARY
                         else V3C.v3_feature_names(V3C.ARM_A))
    else:
        # Fail closed on any count/identity/order drift (Part Z): the
        # preprocessor schema is derived from these names, so it cannot
        # catch a short/foreign list on its own.
        expected = (feature_names_110() if feature_arm == ARM_PRIMARY
                    else V3C.v3_feature_names(V3C.ARM_A))
        if tuple(feature_names) != tuple(expected):
            raise ExperimentConfigError(
                f"{feature_arm}: feature identity drift (got "
                f"{len(feature_names)}, expected {len(expected)})")
    split = RUN.resolve_development_fold(fold_id)
    dataset = V3C.materialize_v3(augmented, fold_id, feature_arm,
                                 tuple(feature_names))
    assert_no_2025_in_frame(dataset.validation_metadata, fold_id)
    schema = DATA.feature_schema(augmented.frame, list(dataset.feature_names))
    timings: dict = {}
    warn_list: list = []
    with TIMING.Timer() as total:
        with TIMING.Timer() as t:
            fitted, estimator, info = fit_family(
                dataset.X_train, dataset.y_train, schema, family, config)
        timings["fit_seconds"] = t.seconds
        timings.update({k: v for k, v in info.items()
                        if k.endswith("_seconds")})
        warn_list.extend(f"convergence: {m}" for m in
                         info["convergence_warnings"])
        validation_frame = augmented.frame.loc[
            dataset.y_validation.index].copy()
        with TIMING.Timer() as t:
            prediction = predict_family(
                fitted, estimator, dataset.X_validation,
                list(validation_frame["state_id"]))
        timings["transform_predict_seconds"] = t.seconds
        with TIMING.Timer() as t:
            aligned = RUN._align_validation(prediction, validation_frame)
        timings["align_seconds"] = t.seconds
        y_true = np.asarray(
            dataset.y_validation.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
        if int((~RUN._finite_mask(aligned)).sum()):
            raise InvalidPredictionError(f"{fold_id}: non-finite predictions")
        resolved = TASKS.resolve_task(TASK)
        with TIMING.Timer() as t:
            metric_payloads, w = RUN.evaluate_row_metrics(
                prediction, tuple(resolved.metrics), y_true, aligned,
                race_ids)
            warn_list.extend(w)
        timings["metric_seconds"] = t.seconds
        ok_metrics = tuple(n for n, p in metric_payloads.items()
                           if p.get("status") == "OK")
        with TIMING.Timer() as t:
            stage_labels = STAGES.stage_partition(
                validation_frame["race_progress_frac"])
            stage_payloads, w = RUN.evaluate_stages(
                prediction, ok_metrics, np.asarray(stage_labels),
                y_true, aligned, race_ids)
            warn_list.extend(w)
        timings["stage_seconds"] = t.seconds
        with TIMING.Timer() as t:
            calibration_payload, w = RUN.evaluate_calibration(
                prediction, y_true, aligned)
            warn_list.extend(w)
        timings["calibration_seconds"] = t.seconds
        with TIMING.Timer() as t:
            race_payload, w = RUN.evaluate_winner_top_k(
                prediction, plain,
                tuple(sorted(set(
                    dataset.validation_metadata["race_id"].astype(str)))))
            warn_list.extend(w)
        timings["topk_seconds"] = t.seconds
        stage_names = list(np.asarray(stage_labels))
    timings["total_seconds"] = total.seconds
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(plain.paths.root)).stdout.strip()
    except Exception:
        commit = "unknown"
    config_doc = EX.build_config(
        TASK, feature_arm, fold_id, model_family=family, seed=SEED,
        git_commit=commit,
        model_parameters=resolved_parameters(family, config),
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config={"method": "none"},
        training_rows=int(dataset.train_counts["eligible"]),
        training_races=int(dataset.train_metadata["race_id"].nunique()),
        validation_rows=int(dataset.validation_counts["eligible"]),
        validation_races=int(
            dataset.validation_metadata["race_id"].nunique()))
    return {"config": config_doc, "dataset": dataset,
            "family": family, "model_config_id": config_id(family, config),
            "config_dict": dict(config),
            "predictions": np.asarray(aligned, dtype=float),
            "prediction_result": prediction,
            "y_true": y_true,
            "race_ids": np.asarray(
                dataset.validation_metadata["race_id"].astype(str)),
            "state_ids": list(validation_frame["state_id"]),
            "stage_labels": stage_names,
            "metrics": metric_payloads, "stages": stage_payloads,
            "calibration": calibration_payload,
            "topk": {"winner_top_k": race_payload},
            "feature_names_hash": hashlib.sha256(
                "\n".join(dataset.feature_names).encode()).hexdigest(),
            "transformed_dim": int(info["transformed_dim"]),
            "convergence_warnings": list(info["convergence_warnings"]),
            "warnings": warn_list, "timings": timings,
            "fitted_preprocessor": fitted, "estimator": estimator,
            "fit_info": info}

# ---------------------------------------------------------------------------
# Inner-fold tuning (Part M; outer validation never influences selection)
# ---------------------------------------------------------------------------

def tune_family(augmented: DATA.CanonicalMatrix, family: str,
                outer_fold: str, feature_arm: str = ARM_PRIMARY,
                feature_names: tuple | None = None) -> dict:
    """Evaluate the preregistered grid on inner folds; select one config."""
    verify_contracts()
    assert_development_fold(outer_fold)
    grid = candidate_grids()[family]
    if feature_names is None:
        feature_names = (feature_names_110() if feature_arm == ARM_PRIMARY
                         else V3C.v3_feature_names(V3C.ARM_A))
    else:
        expected = (feature_names_110() if feature_arm == ARM_PRIMARY
                    else V3C.v3_feature_names(V3C.ARM_A))
        if tuple(feature_names) != tuple(expected):
            raise ExperimentConfigError(
                f"{feature_arm}: feature identity drift (got "
                f"{len(feature_names)}, expected {len(expected)})")
    inner_splits = INNER.resolve_inner_splits(outer_fold)
    resolved_task = TASKS.resolve_task(TASK)
    schema_all = DATA.feature_schema(augmented.frame, list(feature_names))
    scores: dict = {s.inner_fold_id: {} for s in inner_splits}
    records: list = []
    estimator_fits = 0
    for split in inner_splits:
        seasons_tr = set(int(s) for s in split.train_seasons)
        seasons_va = set(int(s) for s in split.validation_seasons)
        if 2025 in seasons_tr or 2025 in seasons_va:
            raise ProtectedHoldoutError(
                f"{split.inner_fold_id}: 2025 reached inner tuning")
        frame_tr = augmented.select_seasons(split.train_seasons)
        frame_va = augmented.select_seasons(split.validation_seasons)
        _, y_tr, _ = SPLITS._apply_mask(frame_tr, resolved_task)
        _, y_va, meta_va = SPLITS._apply_mask(frame_va, resolved_task)
        X_tr = frame_tr.loc[y_tr.index, list(feature_names)].copy()
        X_va = frame_va.loc[y_va.index, list(feature_names)].copy()
        with TIMING.Timer() as t_pre:
            pre = PRE.fit_preprocessor(X_tr, schema_all)
        with TIMING.Timer() as t_tr:
            Z_tr = pre.transform(X_tr)
            Z_va = pre.transform(X_va)
        yv = np.asarray(y_va.astype(float), dtype=float)
        race_ids = np.asarray(meta_va["race_id"].astype(str))
        y_tr_arr = np.asarray(y_tr.astype(float), dtype=float)
        fold_configs: dict = {}
        for cfg in grid:
            key = config_id(family, cfg)
            estimator = build_estimator(family, cfg)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                estimator.fit(Z_tr, y_tr_arr)
            estimator_fits += 1
            proba = np.asarray(estimator.predict_proba(Z_va))[
                :, _positive_index(estimator)]
            value = AGG.race_macro(yv, proba, race_ids, "log_loss")["value"]
            scores[split.inner_fold_id][key] = float(value)
            fold_configs[key] = {"hyperparameters": dict(cfg),
                                 "race_macro_log_loss": float(value)}
        records.append({
            "inner_fold_id": split.inner_fold_id,
            "train_seasons": list(split.train_seasons),
            "validation_seasons": list(split.validation_seasons),
            "preprocessing_fit_seconds": t_pre.seconds,
            "transform_seconds": t_tr.seconds,
            "configs": fold_configs})
        del Z_tr, Z_va, pre
    aggregates: dict = {}
    for cfg in grid:
        key = config_id(family, cfg)
        values = {name: scores[name][key] for name in scores}
        aggregates[key] = {"config": dict(cfg),
                           **AGG.aggregate_folds(values)}
    defined = {k: v for k, v in aggregates.items()
               if v.get("mean") is not None and np.isfinite(v["mean"])}
    if not defined:
        raise ExperimentConfigError(
            f"{family}/{outer_fold}: no finite inner log loss")
    best_mean = min(v["mean"] for v in defined.values())
    within = [k for k, v in defined.items()
              if v["mean"] <= best_mean + TIE_TOLERANCE]
    grid_by_key = {config_id(family, c): c for c in grid}
    chosen = min(within,
                 key=lambda k: complexity_rank(family, grid_by_key[k]))
    selection = {
        "selected_key": chosen,
        "selected_config": dict(grid_by_key[chosen]),
        "selected_mean": defined[chosen]["mean"],
        "best_mean": best_mean,
        "within_tolerance": sorted(within),
        "tie_break_applied": len(within) > 1,
        "objective": "mean inner-fold race-macro log loss",
        "tie_tolerance": TIE_TOLERANCE,
        "tie_rule": "difference <= 1e-6 -> simpler preregistered config",
    }
    return {"family": family, "outer_fold": outer_fold,
            "feature_arm": feature_arm,
            "inner_folds": records, "config_aggregates": aggregates,
            "selection": selection, "estimator_fits": estimator_fits}

# ---------------------------------------------------------------------------
# OOF contract (Part O)
# ---------------------------------------------------------------------------

def build_oof_frame(result: dict, fold_id: str, feature_arm: str,
                    baseline_proba: np.ndarray | None = None) -> pd.DataFrame:
    """Canonical aligned OOF frame; unique identity, stable sort, typed p."""
    n = len(result["state_ids"])
    frame = pd.DataFrame({
        "state_id": list(result["state_ids"]),
        "season": [int(s) for s in
                   result["dataset"].validation_metadata["season"].astype(int)],
        "race_id": list(result["dataset"].validation_metadata["race_id"].astype(str)),
        "driver_id": list(result["dataset"].validation_metadata["driver_id"].astype(str)),
        "target": np.asarray(result["y_true"], dtype=float),
        "fold": [fold_id] * n,
        "stage": list(result["stage_labels"]),
        "feature_arm": [feature_arm] * n,
        "model_family": [result["family"]] * n,
        "model_config_id": [result["model_config_id"]] * n,
        "probability": np.asarray(result["predictions"], dtype=float),
    })
    if baseline_proba is not None:
        frame["baseline_probability"] = np.asarray(baseline_proba,
                                                   dtype=float)
    return frame[list(OOF_COLUMNS) + (
        ["baseline_probability"] if baseline_proba is not None else [])]


def validate_oof_frame(frame: pd.DataFrame,
                       expect_baseline: bool = False) -> dict:
    """Fail-closed OOF validation (Part Z: no silent fallback)."""
    required = list(OOF_COLUMNS) + (
        ["baseline_probability"] if expect_baseline else [])
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ExperimentConfigError(f"OOF missing columns: {missing}")
    if frame.empty:
        raise ExperimentConfigError("OOF frame is empty")
    if frame["state_id"].duplicated().any():
        raise ExperimentConfigError("duplicate OOF state identity")
    if int(frame["state_id"].nunique()) != len(frame):
        raise ExperimentConfigError("OOF state identity not unique")
    p = np.asarray(frame["probability"], dtype=float)
    if not np.all(np.isfinite(p)):
        raise InvalidPredictionError("OOF probability contains NaN/inf")
    if np.any((p < 0.0) | (p > 1.0)):
        raise InvalidPredictionError("OOF probability outside [0, 1]")
    if frame["target"].isna().any():
        raise ExperimentConfigError("OOF missing target")
    if set(np.unique(frame["target"].astype(float))) - {0.0, 1.0}:
        raise ExperimentConfigError("OOF target must be binary 0/1")
    ordered = frame.sort_values(
        ["fold", "race_id", "driver_id", "state_id"],
        kind="mergesort").reset_index(drop=True)
    return {"n_rows": int(len(frame)),
            "n_races": int(frame["race_id"].nunique()),
            "stable_sorted": bool(frame.reset_index(drop=True).equals(
                frame.sort_values(
                    ["fold", "race_id", "driver_id", "state_id"],
                    kind="mergesort").reset_index(drop=True))),
            "sorted_rows": int(len(ordered))}


def write_oof_parquet(frame: pd.DataFrame, name: str) -> Path:
    OOF_DIR.mkdir(parents=True, exist_ok=True)
    dest = OOF_DIR / name
    validate_oof_frame(
        frame, expect_baseline=("baseline_probability" in frame.columns))
    frame.to_parquet(dest, index=False)
    return dest

# ---------------------------------------------------------------------------
# Race-level comparison (Part Q) + diversity support (Part R)
# ---------------------------------------------------------------------------

def race_comparison(baseline_per_race: dict, candidate_per_race: dict,
                    baseline_oof: pd.DataFrame | None = None,
                    candidate_oof: pd.DataFrame | None = None) -> dict:
    """Per-race deltas + paired race bootstrap (B=2000, seed=42, 95% CI)."""
    races = sorted(set(baseline_per_race) & set(candidate_per_race))
    if len(races) < 2:
        raise ExperimentConfigError("comparison needs >= 2 shared races")
    deltas = {r: float(candidate_per_race[r]) - float(baseline_per_race[r])
              for r in races}
    boot = V3C.paired_bootstrap(
        baseline_per_race, candidate_per_race, seed=BOOTSTRAP_SEED,
        replicates=BOOTSTRAP_REPLICATES, ci_level=0.95)
    improved = sum(1 for v in deltas.values() if v < 0.0)
    worsened = sum(1 for v in deltas.values() if v > 0.0)
    out = {
        "n_races": len(races),
        "mean_delta": float(np.mean(list(deltas.values()))),
        "races_improved": int(improved),
        "races_worsened": int(worsened),
        "ties": int(len(races) - improved - worsened),
        "per_race_delta": deltas,
        "bootstrap": {"seed": BOOTSTRAP_SEED,
                      "replicates": BOOTSTRAP_REPLICATES,
                      "ci_level": 0.95,
                      "mean_delta": boot["mean_delta"],
                      "ci_lo": boot["ci_lo"], "ci_hi": boot["ci_hi"]},
        "label": "HARNESS_SMOKE_ONLY (no KEEP/REJECT decisions in B)",
    }
    if baseline_oof is not None and candidate_oof is not None:
        out["diversity"] = diversity_support(baseline_oof, candidate_oof)
    return out


def diversity_support(baseline_oof: pd.DataFrame,
                      candidate_oof: pd.DataFrame) -> dict:
    """Aligned correlation/disagreement inputs for later (V3.3D) use."""
    merged = baseline_oof[["state_id", "probability"]].rename(
        columns={"probability": "p_base"}).merge(
        candidate_oof[["state_id", "probability", "target"]].rename(
            columns={"probability": "p_cand"}),
        on="state_id", validate="one_to_one")
    pb = merged["p_base"].to_numpy()
    pc = merged["p_cand"].to_numpy()
    y = merged["target"].to_numpy(dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        corr = float(np.corrcoef(pb, pc)[0, 1]) if len(merged) > 1 else None
        rb = y - pb
        rc = y - pc
        resid_corr = float(np.corrcoef(rb, rc)[0, 1]) \
            if len(merged) > 1 else None
    return {
        "n_states": int(len(merged)),
        "prediction_correlation": corr,
        "residual_correlation": resid_corr,
        "mean_abs_probability_gap": float(np.mean(np.abs(pb - pc))),
        "note": "alignment inputs only; no ensemble optimization in B",
    }

# ---------------------------------------------------------------------------
# Provenance (Part T), determinism (Part U), serialization (Part Y)
# ---------------------------------------------------------------------------

def library_versions() -> dict:
    import sklearn

    import xgboost
    return {"sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__}


def provenance_envelope(*, family: str, config: dict, fold_id: str,
                        feature_arm: str, feature_names: tuple,
                        dataset, code_commit: str) -> dict:
    contracts = verify_contracts()
    return {
        "a_contract_sha": contracts["contract_sha"],
        "b_prereg_sha": contracts["prereg_sha"],
        "dataset_identity": {
            "matrix_content_hash": "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",
            "dynamics_content_sha": V3C.V3_DYNAMICS_LOGICAL_SHA,
        },
        "feature_identity": {
            "feature_arm": feature_arm,
            "feature_count": len(feature_names),
            "feature_hash": hashlib.sha256(
                "\n".join(feature_names).encode()).hexdigest(),
        },
        "task_identity": {"task": TASK, "label": "is_winner",
                          "semantics": "INDEPENDENT_BINARY"},
        "fold_identity": {"fold": fold_id,
                          "train_seasons": list(dataset.split.train_seasons),
                          "validation_seasons": list(
                              dataset.split.validation_seasons)},
        "model_family": family,
        "model_config_id": config_id(family, config),
        "hyperparameters": resolved_parameters(family, config),
        "library_versions": library_versions(),
        "seed": SEED,
        "thread_policy": dict(THREAD_POLICY),
        "code_version": code_commit,
        "calibration": "RAW",
    }


def determinism_check(family: str, config: dict,
                      X_train: pd.DataFrame, y_train: pd.Series,
                      schema: DATA.FeatureSchema,
                      X_val: pd.DataFrame) -> dict:
    """Two identical fits; stable probabilities within tolerance."""
    _, est_a, _ = fit_family(X_train, y_train, schema, family, config)
    fitted_b, est_b, _ = fit_family(X_train, y_train, schema, family, config)
    pa = np.asarray(est_a.predict_proba(
        fitted_b.transform(X_val)))[:, _positive_index(est_a)]
    pb = np.asarray(est_b.predict_proba(
        fitted_b.transform(X_val)))[:, _positive_index(est_b)]
    diff = float(np.max(np.abs(pa - pb)))
    tolerance = 1e-9 if family == "logistic_regression" else 1e-6
    return {"family": family, "config_id": config_id(family, config),
            "max_abs_probability_difference": diff,
            "tolerance": tolerance,
            "stable": bool(diff <= tolerance),
            "note": "tree ensembles: bit-exact CPU behavior not guaranteed "
                    "across BLAS/OpenMP builds; 1e-6 smoke tolerance"}


def serialization_roundtrip(family: str, config: dict,
                            fitted, estimator,
                            X_val: pd.DataFrame,
                            tolerance: float = 1e-12) -> dict:
    """joblib dump/load preserves predictions within tolerance."""
    import joblib
    import tempfile

    OOF_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            suffix=".joblib", dir=str(OOF_DIR), delete=False) as fh:
        path = fh.name
    try:
        joblib.dump({"estimator": estimator, "preprocessor": fitted,
                     "family": family, "config": dict(config)}, path)
        restored = joblib.load(path)
        before = np.asarray(estimator.predict_proba(
            fitted.transform(X_val)))[:, _positive_index(estimator)]
        after = np.asarray(restored["estimator"].predict_proba(
            restored["preprocessor"].transform(X_val)))[
            :, _positive_index(restored["estimator"])]
        diff = float(np.max(np.abs(before - after)))
    finally:
        Path(path).unlink(missing_ok=True)
    return {"family": family, "config_id": config_id(family, config),
            "max_abs_probability_difference": diff,
            "tolerance": tolerance,
            "equivalent": bool(diff <= tolerance)}
