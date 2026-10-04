"""V3.1C controlled temporal experiment harness (dynamics representation test).

Reuses frozen Model Lab machinery end to end: splits, task resolution,
preprocessing, estimator construction, typed predictions, metric /
stage / calibration / top-k evaluation, experiment identity. The only
new code here is V3-specific plumbing: sidecar join, named V3 feature
sets, C=0.01 estimator wiring, paired race bootstrap, and the 2025
firewall. No metric, split, calibration, top-k, or preprocessing
semantics are redefined.

Arms (all: winner task, LogReg C=0.01 RAW, D1/D2/D3):
  ARM A  ALL_84 (control; must reproduce frozen development values)
  ARM B  ALL_84_PLUS_V3_1_DYNAMICS_CORE (primary representation test)
  ARM C  V3_1_DYNAMICS_CORE only (standalone-signal diagnostic)

2025 holdout is unreachable: folds resolve exclusively through
``runner.resolve_development_fold`` (HOLDOUT/2025 raise
ProtectedHoldoutError, no opt-in) plus an explicit season guard.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.config import V2Paths
from raceintel.features import build_matrix as F15
from raceintel.features.dynamics import build as DYN_BUILD
from raceintel.features.dynamics import contract as DYN_CONTRACT
from raceintel.features.dynamics import validation as DYN_VAL
from raceintel.model_lab import calibration as CAL  # noqa: F401 (re-export guard)
from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import metrics as MET  # noqa: F401 (re-export guard)
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab import tasks as TASKS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutError,
)

#: V3.1C frozen identities (must match V3.1A-C1 / V3.1B exactly).
V3_CONTRACT_VERSION = "v3.1a-v2"
V3_CONTRACT_SHA = (
    "abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4")
V3_DYNAMICS_LOGICAL_SHA = (
    "40ef05809e2932d725785a0e991bcecede8d884f2388affec3f56147611696a1")

#: Named V3.1C feature sets (immutable resolution; VARIANT_A excluded:
#: provisional features run only under predeclared V3.1A authorization).
ARM_A = "ALL_84"
ARM_B = "ALL_84_PLUS_V3_1_DYNAMICS_CORE"
ARM_C = "V3_1_DYNAMICS_CORE"
V3_ARMS = (ARM_A, ARM_B, ARM_C)

#: Frozen model specification (V3.1A Part G; identical for every arm/fold).
V3_TASK = "winner"
V3_MODEL_FAMILY = "logistic_regression"
V3_MODEL_PARAMETERS = {
    "C": 0.01,
    "class_weight": None,
    "estimator": "LogisticRegression",
    "max_iter": 1000,
    "penalty": "l2",
    "random_state": 42,
    "solver": "lbfgs",
}
V3_SEED = 42
V3_CALIBRATION = {"method": "none"}

#: Frozen statistical contract (V3.1A): paired race bootstrap.
BOOTSTRAP_SEED = 42
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_CI_LEVEL = 0.95

#: Folds owned by V3.1C (development only; 2025 unreachable by construction).
V3_FOLDS = ("D1", "D2", "D3")

#: Predeclared history-depth bins for missingness diagnostics (diagnostic
#: only; fixed before results, never tuned).
DEPTH_BINS = (("thin", 0, 2), ("medium", 3, 6), ("full", 7, 10))


def v3_feature_names(kind: str, canonical_84: tuple | None = None) -> tuple:
    """Immutable named V3.1C feature-set resolution (no ad-hoc subsets)."""
    if kind == ARM_A:
        if canonical_84 is None:
            from raceintel.experiments.feature_sets import (
                canonical_predictive_names,
            )
            canonical_84 = canonical_predictive_names()
        return tuple(canonical_84)
    if kind == ARM_C:
        return tuple(DYN_CONTRACT.feature_set_names("core"))
    if kind == ARM_B:
        base = v3_feature_names(ARM_A, canonical_84)
        core = v3_feature_names(ARM_C)
        overlap = set(base) & set(core)
        if overlap:
            raise ExperimentConfigError(
                f"V3 CORE overlaps ALL_84: {sorted(overlap)}")
        return tuple(base) + tuple(core)
    raise ExperimentConfigError(f"unknown V3.1C feature set {kind!r}")


def check_v3_identities() -> dict:
    """Fail closed unless every frozen V3.1 input identity is exact."""
    if DYN_CONTRACT.CONTRACT_VERSION != V3_CONTRACT_VERSION:
        raise ExperimentConfigError(
            f"dynamics contract {DYN_CONTRACT.CONTRACT_VERSION!r} != "
            f"{V3_CONTRACT_VERSION!r}")
    sha = DYN_CONTRACT.contract_hash()
    if sha != V3_CONTRACT_SHA:
        raise ExperimentConfigError("dynamics contract SHA mismatch")
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = canonical_predictive_names()
    if len(names_84) != 84:
        raise ExperimentConfigError("ALL_84 != 84")
    core = v3_feature_names(ARM_C)
    if len(core) != 26:
        raise ExperimentConfigError("V3 CORE != 26")
    combined = v3_feature_names(ARM_B, names_84)
    if len(combined) != 110:
        raise ExperimentConfigError("combined != 110")
    return {"contract_version": V3_CONTRACT_VERSION,
            "contract_sha": sha,
            "all_84": 84, "core": 26, "combined": 110}


def load_joined_frame(paths=None) -> tuple:
    """Frozen Phase-2 matrix + V3.1B sidecar, exact 1:1 join, verified.

    Returns (augmented CanonicalMatrix, plain CanonicalMatrix). The
    augmented manifest carries predictive_columns = 84 + 26 CORE so the
    frozen schema router (float64/Int64 -> numeric, boolean -> boolean)
    classifies dynamics columns mechanically. Label/mask/identity
    columns are untouched from the frozen matrix.
    """
    check_v3_identities()
    paths = V2Paths.resolve(paths)
    matrix, manifest = F15.load_matrix(paths)
    content = F15.content_hash(matrix)
    DYN_VAL.check_parent_identities(
        content, DYN_BUILD.sha256_file(DYN_BUILD.parquet_path(paths)))
    dest = DYN_BUILD.default_out_dir(paths.root)
    sidecar = pd.read_parquet(dest / DYN_BUILD.DYNAMICS_FILE)
    prov = json.loads((dest / DYN_BUILD.PROVENANCE_FILE).read_text())
    if prov.get("contract_version") != V3_CONTRACT_VERSION or \
            prov.get("contract_sha") != V3_CONTRACT_SHA:
        raise ExperimentConfigError("sidecar provenance contract mismatch")
    if prov.get("logical_content_sha") != V3_DYNAMICS_LOGICAL_SHA:
        raise ExperimentConfigError("sidecar logical content SHA mismatch")
    if DYN_BUILD.content_hash(sidecar) != V3_DYNAMICS_LOGICAL_SHA:
        raise ExperimentConfigError(
            "sidecar recomputed content SHA mismatch")
    dyn_names = list(DYN_CONTRACT.feature_set_names("all"))
    missing = [n for n in dyn_names if n not in sidecar.columns]
    if missing:
        raise ExperimentConfigError(f"sidecar missing columns: {missing}")
    joined = matrix.merge(
        sidecar[["state_id"] + dyn_names].astype(
            {c: sidecar[c].dtype for c in ["state_id"] + dyn_names}),
        on="state_id", how="left", validate="one_to_one", indicator=True)
    unmatched = joined[joined["_merge"] != "both"]
    if len(unmatched):
        raise ExperimentConfigError(
            f"{len(unmatched)} matrix rows lack sidecar coverage")
    joined = joined.drop(columns=["_merge"])
    aug_manifest = dict(manifest)
    aug_manifest["predictive_columns"] = (
        list(manifest["predictive_columns"])
        + list(DYN_CONTRACT.feature_set_names("core")))
    plain = DATA.CanonicalMatrix(paths, matrix, manifest)
    augmented = DATA.CanonicalMatrix(paths, joined, aug_manifest)
    return augmented, plain


def materialize_v3(augmented: DATA.CanonicalMatrix, fold_id: str,
                   feature_set: str,
                   feature_names: tuple) -> SPLITS.ExperimentDataset:
    """Fold materialization over explicit V3 feature names.

    Mirrors ``splits.materialize`` step for step (mask-first, M0 audit,
    X/y + identity) but takes resolved V3 names instead of registry
    resolution, which only knows the frozen 84. Rejects every non-D1-D3
    fold (2025 firewall) before touching data.
    """
    split = RUN.resolve_development_fold(fold_id)
    if feature_set not in V3_ARMS:
        raise ExperimentConfigError(
            f"unknown V3.1C feature set {feature_set!r}")
    resolved = TASKS.resolve_task(V3_TASK)
    SPLITS.validate_split(augmented, split)
    full_train = augmented.select_seasons(split.train_seasons)
    full_val = (augmented.select_seasons(split.validation_seasons)
                if split.validation_seasons
                else full_train.iloc[0:0].copy())
    _, y_train, meta_train = SPLITS._apply_mask(full_train, resolved)
    _, y_val, meta_val = SPLITS._apply_mask(full_val, resolved)
    train_elig = len(y_train)
    val_elig = len(y_val)
    train_pos = int(y_train.astype("boolean").sum())
    val_pos = int(y_val.astype("boolean").sum())
    if split.is_development:
        SPLITS._assert_m0_counts(split.fold_id, "train", V3_TASK,
                                 train_elig, train_pos)
        SPLITS._assert_m0_counts(split.fold_id, "validation", V3_TASK,
                                 val_elig, val_pos)
    unknown = [n for n in feature_names if n not in full_train.columns]
    if unknown:
        raise ExperimentConfigError(
            f"features absent from joined frame: {unknown[:5]}")
    X_train = full_train.loc[y_train.index, list(feature_names)].copy()
    X_val = (full_val.loc[y_val.index, list(feature_names)].copy()
             if len(y_val) else full_val[list(feature_names)].copy())
    RUN._check_no_holdout_rows(meta_val, fold_id)
    return SPLITS.ExperimentDataset(
        task=V3_TASK, fold_id=fold_id, feature_set=feature_set,
        feature_names=tuple(feature_names), split=split,
        X_train=X_train, y_train=y_train, train_metadata=meta_train,
        X_validation=X_val, y_validation=y_val,
        validation_metadata=meta_val,
        train_counts={"states": int(len(full_train)),
                      "eligible": train_elig, "positives": train_pos,
                      "coverage": int(y_train.notna().sum())},
        validation_counts={"states": int(len(full_val)),
                           "eligible": val_elig, "positives": val_pos,
                           "coverage": int(y_val.notna().sum())})


def fit_v3_params(X_train: pd.DataFrame, y_train: pd.Series,
                  schema: DATA.FeatureSchema, params: dict) -> tuple:
    """TRAIN-only preprocessor + estimator fit with explicit params.

    The experimental default is the frozen C=0.01 spec; a different C is
    accepted solely for the Arm A fidelity gate (M7 per-fold values).
    """
    target = np.asarray(y_train.astype(float)).ravel()
    if set(np.unique(target)) - {0.0, 1.0}:
        raise ExperimentConfigError("winner target must be binary 0/1")
    with TIMING.Timer() as t:
        fitted = PRE.fit_preprocessor(X_train, schema)
    prep_seconds = t.seconds
    with TIMING.Timer() as t:
        train_matrix = fitted.transform(X_train)
    transform_seconds = t.seconds
    estimator = TC.build_estimator(V3_MODEL_FAMILY, {"C": params["C"]})
    caught_messages: list = []
    with TIMING.Timer() as t:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            estimator.fit(train_matrix, target)
            for item in caught:
                caught_messages.append(
                    f"{item.category.__name__}: {str(item.message)}")
    fit_seconds = t.seconds
    classes = list(estimator.classes_)
    if 1 not in classes:
        raise InvalidPredictionError(
            f"estimator classes {classes} lack positive class 1")
    coef = np.asarray(estimator.coef_).ravel()
    intercept = np.asarray(estimator.intercept_).ravel()
    sanity = {
        "n_coefficients": int(coef.size),
        "transformed_dim": int(fitted.output_dim),
        "all_zero": bool(np.all(coef == 0.0)),
        "any_nan": bool(np.any(~np.isfinite(coef))),
        "intercept_finite": bool(np.all(np.isfinite(intercept))),
        "max_abs_coef": float(np.max(np.abs(coef))) if coef.size else None,
    }
    if sanity["all_zero"] or sanity["any_nan"] \
            or not sanity["intercept_finite"]:
        raise InvalidPredictionError(f"coefficient sanity failed: {sanity}")
    info = {"preprocessing_fit_seconds": prep_seconds,
            "transform_train_seconds": transform_seconds,
            "estimator_fit_seconds": fit_seconds,
            "convergence_warnings": caught_messages,
            "sanity": sanity,
            "positive_index": int(classes.index(1))}
    return fitted, estimator, info


def predict_v3(fitted: PRE.FittedPreprocessor, estimator,
               X_val: pd.DataFrame, state_ids: list,
               positive_index: int) -> PR.PredictionResult:
    """RAW positive-class probabilities as typed INDEPENDENT_BINARY."""
    matrix = fitted.transform(X_val)
    proba = np.asarray(estimator.predict_proba(matrix))[:, positive_index]
    if not np.all(np.isfinite(proba)):
        raise InvalidPredictionError("non-finite V3 LogReg probabilities")
    if np.any((proba < 0.0) | (proba > 1.0)):
        raise InvalidPredictionError("V3 probabilities outside [0, 1]")
    return PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(state_ids),
        values=np.asarray(proba, dtype=float),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY,
        positive_class=1)


def run_v3_arm(augmented: DATA.CanonicalMatrix,
               plain: DATA.CanonicalMatrix, fold_id: str,
               feature_set: str, feature_names: tuple,
               model_c: float = V3_MODEL_PARAMETERS["C"]) -> dict:
    """One arm/fold: materialize, fit TRAIN-only, predict, evaluate.

    Evaluation reuses the canonical runner chain (applicability-guarded
    row metrics, frozen stage partition, ECE calibration, synchronized
    winner top-k over the plain canonical matrix). ``model_c`` exists
    solely for the Arm A fidelity gate (M7 per-fold C values); every
    experimental arm uses the frozen C=0.01 default.
    """
    timings: dict = {}
    warnings_list: list = []
    with TIMING.Timer() as total:
        with TIMING.Timer() as t:
            dataset = materialize_v3(augmented, fold_id, feature_set,
                                     feature_names)
        timings["materialize_seconds"] = t.seconds
        schema = DATA.feature_schema(augmented.frame,
                                     list(dataset.feature_names))
        params = dict(V3_MODEL_PARAMETERS)
        if model_c != V3_MODEL_PARAMETERS["C"]:
            params = dict(params, C=model_c)
        with TIMING.Timer() as t:
            fitted, estimator, info = fit_v3_params(
                dataset.X_train, dataset.y_train, schema, params)
        timings["fit_seconds"] = t.seconds
        timings.update({k: v for k, v in info.items()
                        if k.endswith("_seconds")})
        warnings_list.extend(f"convergence: {m}" for m in
                             info["convergence_warnings"])
        validation_frame = augmented.frame.loc[
            dataset.y_validation.index].copy()
        if list(validation_frame.index) != \
                list(dataset.y_validation.index):
            raise ExperimentConfigError("validation frame index mismatch")
        with TIMING.Timer() as t:
            prediction = predict_v3(
                fitted, estimator, dataset.X_validation,
                list(validation_frame["state_id"]),
                info["positive_index"])
        timings["transform_predict_seconds"] = t.seconds
        with TIMING.Timer() as t:
            aligned = RUN._align_validation(prediction, validation_frame)
        timings["align_seconds"] = t.seconds
        y_true = np.asarray(
            dataset.y_validation.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
        if int((~RUN._finite_mask(aligned)).sum()):
            raise InvalidPredictionError(
                f"{fold_id}: non-finite aligned predictions")
        resolved = TASKS.resolve_task(V3_TASK)
        with TIMING.Timer() as t:
            metric_names = tuple(resolved.metrics)
            metric_payloads, w = RUN.evaluate_row_metrics(
                prediction, metric_names, y_true, aligned, race_ids)
            warnings_list.extend(w)
        timings["metric_seconds"] = t.seconds
        ok_metrics = tuple(n for n, p in metric_payloads.items()
                           if p.get("status") == "OK")
        with TIMING.Timer() as t:
            stage_labels = STAGES.stage_partition(
                validation_frame["race_progress_frac"])
            stage_payloads, w = RUN.evaluate_stages(
                prediction, ok_metrics, np.asarray(stage_labels),
                y_true, aligned, race_ids)
            warnings_list.extend(w)
        timings["stage_seconds"] = t.seconds
        with TIMING.Timer() as t:
            calibration_payload, w = RUN.evaluate_calibration(
                prediction, y_true, aligned)
            warnings_list.extend(w)
        timings["calibration_seconds"] = t.seconds
        with TIMING.Timer() as t:
            race_payload, w = RUN.evaluate_winner_top_k(
                prediction, plain,
                tuple(sorted(set(
                    dataset.validation_metadata["race_id"].astype(str)))))
            warnings_list.extend(w)
        timings["topk_seconds"] = t.seconds
        race_ids_plain = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
    timings["total_seconds"] = total.seconds
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(plain.paths.root)).stdout.strip()
    except Exception:
        commit = "unknown"
    config = EX.build_config(
        V3_TASK, feature_set, fold_id, model_family=V3_MODEL_FAMILY,
        seed=V3_SEED, git_commit=commit,
        model_parameters=params,
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config=dict(V3_CALIBRATION),
        training_rows=int(dataset.train_counts["eligible"]),
        training_races=int(dataset.train_metadata["race_id"].nunique()),
        validation_rows=int(dataset.validation_counts["eligible"]),
        validation_races=int(
            dataset.validation_metadata["race_id"].nunique()))
    return {"config": config, "dataset": dataset, "params": params,
            "predictions": np.asarray(aligned, dtype=float),
            "prediction_result": prediction,
            "y_true": y_true, "race_ids": race_ids_plain,
            "state_ids": list(validation_frame["state_id"]),
            "metrics": metric_payloads, "stages": stage_payloads,
            "calibration": calibration_payload,
            "topk": {"winner_top_k": race_payload},
            "sanity": info["sanity"],
            "feature_names_hash": hashlib.sha256(
                "\n".join(dataset.feature_names).encode()).hexdigest(),
            "transformed_dim": int(info["sanity"]["transformed_dim"]),
            "convergence_warnings": list(info["convergence_warnings"]),
            "warnings": warnings_list, "timings": timings}


def paired_bootstrap(per_race_a: dict, per_race_b: dict, *,
                     seed: int = BOOTSTRAP_SEED,
                     replicates: int = BOOTSTRAP_REPLICATES,
                     ci_level: float = BOOTSTRAP_CI_LEVEL) -> dict:
    """Paired race-level bootstrap over LL_B - LL_A (deterministic).

    Resamples races with replacement (never states). Returns the observed
    paired deltas plus percentile CI. Negative delta = B better.
    """
    races = sorted(set(per_race_a) & set(per_race_b))
    if len(races) < 2:
        raise ExperimentConfigError("bootstrap needs >= 2 shared races")
    deltas = np.array([float(per_race_b[r]) - float(per_race_a[r])
                       for r in races], dtype=float)
    if not np.all(np.isfinite(deltas)):
        raise ExperimentConfigError("non-finite per-race deltas")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(deltas), size=(replicates, len(deltas)))
    means = deltas[draws].mean(axis=1)
    lo_q = (1.0 - ci_level) / 2.0 * 100.0
    hi_q = (1.0 + ci_level) / 2.0 * 100.0
    return {
        "n_races": int(len(races)),
        "replicates": int(replicates),
        "seed": int(seed),
        "ci_level": float(ci_level),
        "mean_delta": float(np.mean(deltas)),
        "median_delta": float(np.median(deltas)),
        "frac_improved": float(np.mean(deltas < 0.0)),
        "frac_worsened": float(np.mean(deltas > 0.0)),
        "frac_tied": float(np.mean(deltas == 0.0)),
        "ci_lo": float(np.percentile(means, lo_q)),
        "ci_hi": float(np.percentile(means, hi_q)),
        "procedure": "paired race resampling with replacement; "
                     "statistic = mean(LL_B - LL_A); percentile CI",
    }


def assert_no_holdout_request(fold_id: str) -> None:
    """Explicit V3.1C holdout firewall: only D1/D2/D3 may run."""
    if fold_id not in V3_FOLDS:
        raise ProtectedHoldoutError(
            f"V3.1C refuses {fold_id!r}: development folds "
            f"{list(V3_FOLDS)} only; 2025 holdout is sealed")


# ---------------------------------------------------------------------------
# V3.1D sealed-holdout extension (FINAL_FIT + one-shot 2025 evaluation).
#
# Added for the V3.1D freeze stage only. V3.1C functions above are untouched.
# Frozen count anchors mirror final_fit.py FINAL_FIT_EXPECTED (lines 95-98)
# and HOLDOUT_EXPECTED (lines 99-102); hardcoded with citation to avoid
# importing the M9 stage module into the V3 experiment path.
# ---------------------------------------------------------------------------

#: Frozen FINAL_FIT / holdout count anchors (final_fit.py:95-102).
V3_FINAL_FIT_EXPECTED = {
    "races": 149, "states": 162728, "eligible": 162728,
    "positives": 8926, "negatives": 153802,
}
V3_HOLDOUT_EXPECTED = {
    "races": 24, "states": 26692, "eligible": 26692,
    "positives": 1444, "negatives": 25248,
}

#: V3.1D frozen periods.
V3_FINAL_FIT_SEASONS = tuple(range(2018, 2025))
V3_HOLDOUT_SEASON = 2025

#: Preregistration schema version.
PREREG_SCHEMA_VERSION = "v3.1d-prereg-v1"


def _check_counts(observed: dict, expected: dict, label: str) -> None:
    for key, value in expected.items():
        if int(observed.get(key, -1)) != int(value):
            raise ExperimentConfigError(
                f"{label} count drift: {key}={observed.get(key)!r} != "
                f"{value!r}")


def materialize_v3_final_fit(augmented: DATA.CanonicalMatrix,
                             feature_set: str,
                             feature_names: tuple) -> SPLITS.ExperimentDataset:
    """All eligible 2018-2024 winner rows through the frozen mask (V3.1D).

    Mirrors final_fit.materialize_final_fit over explicit V3 feature names.
    Any 2025 row on the train side fails closed.
    """
    if feature_set not in (ARM_A, ARM_B):
        raise ExperimentConfigError(
            f"V3.1D admits arms A/B only; got {feature_set!r}")
    split = SPLITS.get_split(SPLITS.FINAL_FIT_ID)
    if tuple(int(s) for s in split.train_seasons) != V3_FINAL_FIT_SEASONS:
        raise ExperimentConfigError("FINAL_FIT train seasons drift")
    if split.validation_seasons:
        raise ExperimentConfigError("FINAL_FIT must have no validation side")
    resolved = TASKS.resolve_task(V3_TASK)
    SPLITS.validate_split(augmented, split)
    full_train = augmented.select_seasons(split.train_seasons)
    if (full_train["season"].astype(int) == V3_HOLDOUT_SEASON).any():
        raise ProtectedHoldoutError("2025 leaked into FINAL_FIT train side")
    _, y_train, meta_train = SPLITS._apply_mask(full_train, resolved)
    train_elig = len(y_train)
    train_pos = int(y_train.astype("boolean").sum())
    counts = {
        "races": int(meta_train["race_id"].nunique()),
        "states": int(len(full_train)),
        "eligible": train_elig,
        "positives": train_pos,
        "negatives": int(train_elig - train_pos),
    }
    _check_counts(counts, V3_FINAL_FIT_EXPECTED, "V3 FINAL_FIT")
    unknown = [n for n in feature_names if n not in full_train.columns]
    if unknown:
        raise ExperimentConfigError(
            f"features absent from joined frame: {unknown[:5]}")
    X_train = full_train.loc[y_train.index, list(feature_names)].copy()
    return SPLITS.ExperimentDataset(
        task=V3_TASK, fold_id=SPLITS.FINAL_FIT_ID, feature_set=feature_set,
        feature_names=tuple(feature_names), split=split,
        X_train=X_train, y_train=y_train, train_metadata=meta_train,
        X_validation=full_train.iloc[0:0][list(feature_names)].copy(),
        y_validation=y_train.iloc[0:0].copy(),
        validation_metadata=meta_train.iloc[0:0].copy(),
        train_counts={"states": int(len(full_train)),
                      "eligible": train_elig, "positives": train_pos,
                      "coverage": int(y_train.notna().sum())},
        validation_counts={"states": 0, "eligible": 0, "positives": 0,
                           "coverage": 0})


def materialize_v3_holdout(augmented: DATA.CanonicalMatrix, *,
                           allow_protected_holdout: bool = False
                           ) -> SPLITS.ExperimentDataset:
    """Eligible 2025 winner holdout through the frozen mask (explicit opt-in).

    No feature selection here: X columns are resolved by the caller from the
    preregistered arm order. Fails closed without explicit intent.
    """
    if not allow_protected_holdout:
        raise ProtectedHoldoutError(
            "V3.1D holdout requires allow_protected_holdout=True "
            "(preregistered one-shot only)")
    split = SPLITS.get_split(SPLITS.HOLDOUT_ID,
                             allow_protected_holdout=True)
    resolved = TASKS.resolve_task(V3_TASK)
    SPLITS.validate_split(augmented, split)
    full_val = augmented.select_seasons(split.validation_seasons)
    seasons = {int(s) for s in full_val["season"].astype(int).unique()}
    if seasons != {V3_HOLDOUT_SEASON}:
        raise ProtectedHoldoutError(
            f"holdout seasons {seasons} != {{{V3_HOLDOUT_SEASON}}}")
    _, y_val, meta_val = SPLITS._apply_mask(full_val, resolved)
    val_elig = len(y_val)
    val_pos = int(y_val.astype("boolean").sum())
    counts = {
        "races": int(meta_val["race_id"].nunique()),
        "states": int(len(full_val)),
        "eligible": val_elig,
        "positives": val_pos,
        "negatives": int(val_elig - val_pos),
    }
    _check_counts(counts, V3_HOLDOUT_EXPECTED, "V3 HOLDOUT")
    return SPLITS.ExperimentDataset(
        task=V3_TASK, fold_id=SPLITS.HOLDOUT_ID, feature_set="HOLDOUT",
        feature_names=(),
        split=split,
        X_train=full_val.iloc[0:0].copy(), y_train=y_val.iloc[0:0].copy(),
        train_metadata=meta_val.iloc[0:0].copy(),
        X_validation=full_val.copy(), y_validation=y_val,
        validation_metadata=meta_val,
        train_counts={"states": 0, "eligible": 0, "positives": 0,
                      "coverage": 0},
        validation_counts={"states": int(len(full_val)),
                           "eligible": val_elig, "positives": val_pos,
                           "coverage": int(y_val.notna().sum())})


def apply_acceptance_policy(evidence: dict) -> dict:
    """Apply the frozen V3.1 six-clause policy to holdout evidence.

    Pure and deterministic: ``evidence`` carries primary delta, bootstrap
    CI bounds, temporal directions, secondary deltas, ECE delta, and the
    stage-veto assessment. Returns clause outcomes plus the derived
    verdict. No thresholds are invented here: direction uses sign with a
    1e-12 numerical deadband, harm requires the paired CI entirely above
    zero, and ECE non-degradation uses exact non-positivity.
    """
    deadband = 1e-12
    delta = float(evidence["primary_delta_b_a"])
    ci_lo = float(evidence["bootstrap"]["ci_lo"])
    ci_hi = float(evidence["bootstrap"]["ci_hi"])
    clause1_pass = delta < -deadband
    ci_strong = ci_hi < 0.0
    ci_adverse = ci_lo > 0.0
    clause2 = ("strong" if ci_strong else
               "adverse" if ci_adverse else "weak")
    dirs = [float(d) for d in evidence["temporal_directions"]]
    clause3_count = sum(1 for d in dirs if d < -deadband)
    sec = {k: float(v) for k, v in evidence["secondary_deltas"].items()}
    clause4_improved = sorted(
        k for k, v in sec.items()
        if (v < -deadband if k in ("brier",) else
            v > deadband if k in ("roc_auc", "pr_auc") else False))
    ece_delta = float(evidence["ece_delta_b_a"])
    clause5_pass = ece_delta <= 1e-9
    veto = str(evidence["stage_veto"])
    if clause1_pass and clause2 == "strong" and \
            len(clause4_improved) == 3 and clause5_pass and veto == "PASS":
        verdict = "KEEP"
    elif not clause1_pass and clause2 == "adverse":
        verdict = "REJECT"
    elif not clause1_pass:
        verdict = "NULL_RESULT"
    elif veto == "VETO":
        verdict = "REJECT"
    else:
        verdict = "KEEP_WITH_LIMITATION"
    limitations = []
    if verdict == "KEEP_WITH_LIMITATION":
        if clause2 == "weak":
            limitations.append(
                "paired race bootstrap CI spans zero on 2025")
        if not clause5_pass:
            limitations.append(
                f"ECE degradation on 2025 (delta {ece_delta:.6f})")
        if len(clause4_improved) < 3:
            limitations.append(
                "secondary metrics partially inconsistent: "
                + ",".join(sorted(set(sec) - set(clause4_improved))))
        if veto == "CONCERN":
            limitations.append(
                "stage veto CONCERN (see early/history/neutralisation "
                "watch-items)")
        for item in evidence.get("persistent_watch_items", []):
            limitations.append(str(item))
    return {
        "clause1_primary_direction": "pass" if clause1_pass else "fail",
        "clause2_paired_evidence": clause2,
        "clause3_temporal_consistency": {
            "n_improved_of_4": int(clause3_count),
            "classification": f"{clause3_count}/4 improvement"},
        "clause4_secondaries_improved": clause4_improved,
        "clause5_calibration": "pass" if clause5_pass else "degraded",
        "clause6_stage_veto": veto,
        "verdict": verdict,
        "limitations": limitations,
    }


def build_preregistration(names_84: tuple, names_110: tuple,
                          git_commit: str) -> dict:
    """Deterministic V3.1D preregistration (no holdout results inside)."""
    from raceintel.model_lab import preprocessing as _PRE
    spec = {
        "schema_version": PREREG_SCHEMA_VERSION,
        "task": V3_TASK,
        "target": "is_winner",
        "eligibility": "eligible_is_winner",
        "arm_a_feature_set": ARM_A,
        "arm_b_feature_set": ARM_B,
        "arm_a_feature_order": list(names_84),
        "arm_b_feature_order": list(names_110),
        "variant_a": "NOT AUTHORIZED; never resolved as an arm",
        "contract_identity": {
            "contract_version": V3_CONTRACT_VERSION,
            "contract_sha": V3_CONTRACT_SHA},
        "dataset_identities": {
            "phase2_content": "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",  # noqa: E501
            "phase2_parquet": "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3",  # noqa: E501
            "dynamics_content": V3_DYNAMICS_LOGICAL_SHA},
        "training_seasons": list(V3_FINAL_FIT_SEASONS),
        "holdout_season": V3_HOLDOUT_SEASON,
        "preprocessing": _PRE.preprocessing_contract_dict(),
        "model_family": V3_MODEL_FAMILY,
        "hyperparameters": dict(V3_MODEL_PARAMETERS),
        "random_seed": V3_SEED,
        "prediction_semantics": "RAW INDEPENDENT_BINARY (never normalized)",
        "metrics": ["log_loss", "brier", "roc_auc", "pr_auc"],
        "aggregation": "race_macro_headline_state_diagnostic",
        "stages": "race_progress_frac_phase2_thirds (EARLY/MID/LATE)",
        "bootstrap_procedure": {
            "unit": "race (never states)",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "ci_level": BOOTSTRAP_CI_LEVEL,
            "statistic": "mean(LL_B - LL_A)",
            "interval": "percentile"},
        "acceptance_policy": "V3.1 six-clause policy unchanged: (1) 2025 "
                             "primary race-macro LL direction; (2) paired "
                             "race bootstrap; (3) D1/D2/D3/2025 temporal "
                             "consistency; (4) Brier/ROC/PR secondaries; "
                             "(5) ECE non-degradation; (6) stage/complexity "
                             "with predeclared watch-items",
        "watch_items": [
            "D3-EARLY +0.0021 LL regression",
            "thin-history degradation",
            "medium-history degradation",
            "neutralisation-state degradation",
            "D3 bootstrap CI spanning zero"],
        "calibration_policy": "RAW evaluation only (ECE); no fitting, "
                              "no post-hoc transform",
        "one_shot": True,
        "code_commit": git_commit,
    }
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec["preregistration_identity"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    return spec


def run_v3_final(augmented: DATA.CanonicalMatrix,
                 plain: DATA.CanonicalMatrix, feature_set: str,
                 feature_names: tuple) -> dict:
    """V3.1D one-shot: FINAL_FIT fit, single 2025 prediction, evaluation.

    Caller must persist preregistration BEFORE invoking this function and
    must persist returned predictions BEFORE interpreting them. Fitting
    inputs are 2018-2024 only (preprocessing statistics train-only);
    the holdout is resolved through the canonical sealed path with
    explicit opt-in.
    """
    timings: dict = {}
    warnings_list: list = []
    with TIMING.Timer() as total:
        with TIMING.Timer() as t:
            train_ds = materialize_v3_final_fit(
                augmented, feature_set, feature_names)
        timings["materialize_seconds"] = t.seconds
        schema = DATA.feature_schema(augmented.frame,
                                     list(train_ds.feature_names))
        with TIMING.Timer() as t:
            fitted, estimator, info = fit_v3_params(
                train_ds.X_train, train_ds.y_train, schema,
                dict(V3_MODEL_PARAMETERS))
        timings["fit_seconds"] = t.seconds
        timings.update({k: v for k, v in info.items()
                        if k.endswith("_seconds")})
        warnings_list.extend(f"convergence: {m}" for m in
                             info["convergence_warnings"])
        with TIMING.Timer() as t:
            hold_ds = materialize_v3_holdout(
                augmented, allow_protected_holdout=True)
        timings["holdout_materialize_seconds"] = t.seconds
        hold_frame = augmented.frame.loc[
            hold_ds.y_validation.index].copy()
        X_hold = hold_frame.loc[:, list(feature_names)].copy()
        if list(X_hold.index) != list(hold_ds.y_validation.index):
            raise ExperimentConfigError("holdout frame index mismatch")
        with TIMING.Timer() as t:
            prediction = predict_v3(
                fitted, estimator, X_hold,
                list(hold_frame["state_id"]), info["positive_index"])
        timings["transform_predict_seconds"] = t.seconds
        with TIMING.Timer() as t:
            aligned = RUN._align_validation(prediction, hold_frame)
        timings["align_seconds"] = t.seconds
        y_true = np.asarray(
            hold_ds.y_validation.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            hold_ds.validation_metadata["race_id"].astype(str))
        if int((~RUN._finite_mask(aligned)).sum()):
            raise InvalidPredictionError("non-finite holdout predictions")
        resolved = TASKS.resolve_task(V3_TASK)
        with TIMING.Timer() as t:
            metric_payloads, w = RUN.evaluate_row_metrics(
                prediction, tuple(resolved.metrics), y_true, aligned,
                race_ids)
            warnings_list.extend(w)
        timings["metric_seconds"] = t.seconds
        ok_metrics = tuple(n for n, p in metric_payloads.items()
                           if p.get("status") == "OK")
        with TIMING.Timer() as t:
            stage_labels = STAGES.stage_partition(
                hold_frame["race_progress_frac"])
            stage_payloads, w = RUN.evaluate_stages(
                prediction, ok_metrics, np.asarray(stage_labels),
                y_true, aligned, race_ids)
            warnings_list.extend(w)
        timings["stage_seconds"] = t.seconds
        with TIMING.Timer() as t:
            calibration_payload, w = RUN.evaluate_calibration(
                prediction, y_true, aligned)
            warnings_list.extend(w)
        timings["calibration_seconds"] = t.seconds
        with TIMING.Timer() as t:
            race_payload, w = RUN.evaluate_winner_top_k(
                prediction, plain,
                tuple(sorted(set(race_ids))),
                allow_protected_holdout=True)
            warnings_list.extend(w)
        timings["topk_seconds"] = t.seconds
    timings["total_seconds"] = total.seconds
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(plain.paths.root)).stdout.strip()
    except Exception:
        commit = "unknown"
    config = EX.build_config(
        V3_TASK, feature_set, SPLITS.FINAL_FIT_ID,
        model_family=V3_MODEL_FAMILY, seed=V3_SEED, git_commit=commit,
        model_parameters={**dict(V3_MODEL_PARAMETERS),
                          "evaluation_split": SPLITS.HOLDOUT_ID,
                          "final_fit_seasons": list(V3_FINAL_FIT_SEASONS),
                          "holdout_season": V3_HOLDOUT_SEASON},
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config=dict(V3_CALIBRATION),
        training_rows=int(train_ds.train_counts["eligible"]),
        training_races=int(train_ds.train_metadata["race_id"].nunique()),
        validation_rows=int(hold_ds.validation_counts["eligible"]),
        validation_races=int(
            hold_ds.validation_metadata["race_id"].nunique()),
        holdout_accessed=True,
        holdout_purpose="V3.1D one-shot preregistered 2025 evaluation")
    return {"config": config, "train_dataset": train_ds, "holdout_dataset": hold_ds,
            "fitted_preprocessor": fitted, "estimator": estimator,
            "fit_info": info,
            "predictions": np.asarray(aligned, dtype=float),
            "prediction_result": prediction,
            "y_true": y_true, "race_ids": race_ids,
            "state_ids": list(hold_frame["state_id"]),
            "holdout_frame": hold_frame,
            "metrics": metric_payloads, "stages": stage_payloads,
            "calibration": calibration_payload,
            "topk": {"winner_top_k": race_payload},
            "sanity": info["sanity"],
            "feature_names_hash": hashlib.sha256(
                "\n".join(feature_names).encode()).hexdigest(),
            "transformed_dim": int(info["sanity"]["transformed_dim"]),
            "convergence_warnings": list(info["convergence_warnings"]),
            "warnings": warnings_list, "timings": timings}
