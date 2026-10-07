"""V3.3D controlled refinement + temporal calibration (ET + XGB only).

Q1 (ET): does temporally valid calibration + narrow refinement convert
useful disagreement / D2 discrimination into a useful probability model?
Q2 (XGB): does it convert the near-tied primary + distinct race errors
into a credible standalone/diversity candidate? Negative answers valid.

HGB is CLOSED (C: REJECT_NO_IMPROVEMENT); logistic is the untouched
control. C RAW results are read-only references. Calibration data is
cross-fitted within outer TRAIN history only (inner-val predictions);
outer validation never fits/selects anything. 2025 never touched.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import data as DATA
from raceintel.model_lab import inner_splits as INNER
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import tasks as TASKS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ProtectedHoldoutError,
)

#: D candidate set (C advancement; HGB closed, logistic is control).
D_FAMILIES = ("extra_trees", "xgboost")
CLOSED_FAMILIES = ("hist_gradient_boosting", "logistic_regression")

#: Calibration selection: LL gain beyond this + no Brier harm (A rule).
CAL_LL_MARGIN = 1e-4

#: Support gates (Part H): isotonic needs rich support; sigmoid less.
ISOTONIC_MIN_ROWS = 10000
ISOTONIC_MIN_POSITIVES = 500
ISOTONIC_MIN_UNIQUE = 50
SIGMOID_MIN_ROWS = 1000
SIGMOID_MIN_POSITIVES = 50
SIGMOID_MIN_UNIQUE = 10


def require_d_family(family: str) -> None:
    if family in CLOSED_FAMILIES:
        raise ExperimentConfigError(
            f"D refuses {family!r}: HGB is CLOSED, logistic is control; "
            f"D admits {list(D_FAMILIES)} only")
    if family not in D_FAMILIES:
        raise ExperimentConfigError(
            f"unknown D family {family!r}; admitted: {list(D_FAMILIES)}")


def d_grids() -> dict:
    """<=6 NEW refinement configs per family, C-evidence justified.

    ET: C selected sqrt on every fold (0.5 never competitive) -> freeze
    sqrt; msl=5 beats 1 on D2/D3 inner, 1 wins D1 -> probe neighbors
    {3, 10} + complete the selected-value cross + intermediate depth 10.
    XGB: stable 0.05/d3/mcw5 on all folds (lr=0.1, depth=5 clearly
    worse) -> probe lr/mcw neighbors, one-step-deeper depth 4,
    estimator-count stability (n=500), shallow+fast corner (0.1/d2).
    All configs are distinct from the C grids.
    """
    et = [
        {"max_features": "sqrt", "min_samples_leaf": 3, "max_depth": None,
         "_rationale": "msl neighbor between C-selected 1 and 5"},
        {"max_features": "sqrt", "min_samples_leaf": 3, "max_depth": 20,
         "_rationale": "msl neighbor with bounded depth"},
        {"max_features": "sqrt", "min_samples_leaf": 10, "max_depth": None,
         "_rationale": "stronger regularization than C-selected"},
        {"max_features": "sqrt", "min_samples_leaf": 10, "max_depth": 20,
         "_rationale": "stronger regularization with bounded depth"},
        {"max_features": "sqrt", "min_samples_leaf": 5, "max_depth": 10,
         "_rationale": "intermediate depth between selected None and 20"},
        {"max_features": "sqrt", "min_samples_leaf": 3, "max_depth": 10,
         "_rationale": "middle of both axes (msl neighbor, mid depth); "
                       "tests the unresolved interior"},
    ]
    xgb = [
        {"learning_rate": 0.03, "max_depth": 3, "min_child_weight": 5,
         "_rationale": "gentler learning, same structure as selection"},
        {"learning_rate": 0.05, "max_depth": 3, "min_child_weight": 3,
         "_rationale": "mcw neighbor bracketed by tested 1 and 5"},
        {"learning_rate": 0.05, "max_depth": 3, "min_child_weight": 10,
         "_rationale": "heavier regularization than selection"},
        {"learning_rate": 0.05, "max_depth": 4, "min_child_weight": 5,
         "_rationale": "one step deeper; depth 5 was clearly worse"},
        {"learning_rate": 0.05, "max_depth": 3, "min_child_weight": 5,
         "n_estimators": 500,
         "_rationale": "estimator-count variance-stability probe"},
        {"learning_rate": 0.1, "max_depth": 2, "min_child_weight": 5,
         "_rationale": "shallow+fast corner; depth 2 unseen in C"},
    ]
    return {"extra_trees": et, "xgboost": xgb}


def d_config_id(family: str, config: dict) -> str:
    require_d_family(family)
    clean = {k: v for k, v in config.items() if not k.startswith("_")}
    base = H.config_id(family, {k: v for k, v in clean.items()
                                if k in H.candidate_registry()[family][
                                    "parameter_namespace"]})
    extra = ",".join(f"{k}={v}" for k, v in sorted(clean.items())
                     if k not in H.candidate_registry()[family][
                         "parameter_namespace"])
    return base + ("+" + extra if extra else "")


def d_complexity_rank(family: str, config: dict) -> tuple:
    require_d_family(family)
    clean = {k: v for k, v in config.items() if not k.startswith("_")}
    namespace = {k: v for k, v in clean.items()
                 if k in H.candidate_registry()[family][
                     "parameter_namespace"]}
    rank = H.complexity_rank(family, namespace)
    extra_n = int(clean.get("n_estimators", 300))
    return rank + (extra_n,)


def build_d_estimator(family: str, config: dict):
    """D estimator (HGB/logreg refused; xgb accepts n_estimators probe)."""
    require_d_family(family)
    clean = {k: v for k, v in config.items() if not k.startswith("_")}
    if family == "xgboost" and "n_estimators" in clean:
        from xgboost import XGBClassifier
        params = dict(H.candidate_registry()["xgboost"][
            "fixed_parameters"])
        params["n_estimators"] = int(clean["n_estimators"])
        return XGBClassifier(
            objective=params["objective"], eval_metric=params["eval_metric"],
            n_estimators=params["n_estimators"],
            learning_rate=clean["learning_rate"],
            max_depth=clean["max_depth"],
            min_child_weight=clean["min_child_weight"],
            subsample=params["subsample"],
            colsample_bytree=params["colsample_bytree"],
            reg_alpha=params["reg_alpha"], reg_lambda=params["reg_lambda"],
            tree_method=params["tree_method"], n_jobs=params["n_jobs"],
            random_state=params["random_state"])
    return H.build_estimator(family, clean)


def resolved_d_parameters(family: str, config: dict) -> dict:
    require_d_family(family)
    clean = {k: v for k, v in config.items() if not k.startswith("_")}
    base = H.resolved_parameters(family, {
        k: v for k, v in clean.items()
        if k in H.candidate_registry()[family]["parameter_namespace"]})
    for k, v in clean.items():
        if k not in base:
            base[k] = v
    return base

# ---------------------------------------------------------------------------
# Temporal calibration data (Part G): cross-fitted inner-val predictions.
# ---------------------------------------------------------------------------

def calibration_frames(family: str, config: dict,
                       augmented: DATA.CanonicalMatrix,
                       outer_fold: str,
                       feature_names: tuple) -> pd.DataFrame:
    """Cross-fitted (p, y, race, season) over outer TRAIN history only.

    For each inner split: fit base on inner-train, predict inner-val.
    Outer validation is never touched; 2025 raises fail-closed.
    """
    require_d_family(family)
    H.assert_development_fold(outer_fold)
    resolved = TASKS.resolve_task(H.TASK)
    schema = DATA.feature_schema(augmented.frame, list(feature_names))
    rows = []
    for split in INNER.resolve_inner_splits(outer_fold):
        for season in (*split.train_seasons, *split.validation_seasons):
            if int(season) == 2025:
                raise ProtectedHoldoutError(
                    f"{split.inner_fold_id}: 2025 in calibration data")
        frame_tr = augmented.select_seasons(split.train_seasons)
        frame_va = augmented.select_seasons(split.validation_seasons)
        _, y_tr, _ = SPLITS._apply_mask(frame_tr, resolved)
        _, y_va, meta_va = SPLITS._apply_mask(frame_va, resolved)
        X_tr = frame_tr.loc[y_tr.index, list(feature_names)].copy()
        X_va = frame_va.loc[y_va.index, list(feature_names)].copy()
        pre = PRE.fit_preprocessor(X_tr, schema)
        Z_tr, Z_va = pre.transform(X_tr), pre.transform(X_va)
        est = build_d_estimator(family, config)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            est.fit(Z_tr, np.asarray(y_tr.astype(float)))
        proba = np.asarray(est.predict_proba(Z_va))[
            :, H._positive_index(est)]
        rows.append(pd.DataFrame({
            "probability": proba,
            "target": np.asarray(y_va.astype(float)),
            "race_id": meta_va["race_id"].astype(str).to_numpy(),
            "season": meta_va["season"].astype(int).to_numpy(),
            "inner_fold": split.inner_fold_id}))
        del Z_tr, Z_va, pre, est
    cal = pd.concat(rows, ignore_index=True).sort_values(
        ["season", "race_id"], kind="mergesort").reset_index(drop=True)
    return cal


def support_audit(cal: pd.DataFrame, method: str) -> dict:
    """Part H gates: mark NOT_RUN_INSUFFICIENT_SUPPORT when inadequate."""
    n = len(cal)
    positives = int((cal["target"] == 1.0).sum())
    unique = int(pd.Series(cal["probability"]).nunique())
    if method == "isotonic":
        ok = n >= ISOTONIC_MIN_ROWS and positives >= ISOTONIC_MIN_POSITIVES \
            and unique >= ISOTONIC_MIN_UNIQUE
    elif method == "sigmoid":
        ok = n >= SIGMOID_MIN_ROWS and positives >= SIGMOID_MIN_POSITIVES \
            and unique >= SIGMOID_MIN_UNIQUE
    else:
        raise ExperimentConfigError(f"unknown calibration {method!r}")
    return {"method": method, "n_rows": n, "n_positives": positives,
            "n_unique_predictions": unique,
            "status": "OK" if ok else "NOT_RUN_INSUFFICIENT_SUPPORT"}


def fit_platt(p: np.ndarray, y: np.ndarray):
    """Sigmoid (Platt) scaling fitted on fixed predictions."""
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(np.asarray(p, dtype=float).reshape(-1, 1),
                  np.asarray(y, dtype=float).ravel())
    return ("sigmoid", model)


def fit_isotonic(p: np.ndarray, y: np.ndarray):
    """Isotonic regression fitted on fixed predictions (clip OOB)."""
    from sklearn.isotonic import IsotonicRegression
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(np.asarray(p, dtype=float),
                  np.asarray(y, dtype=float).ravel())
    return ("isotonic", model)


def apply_calibrator(calibrator, p: np.ndarray) -> np.ndarray:
    import numpy as _np
    method, model = calibrator
    x = _np.asarray(p, dtype=float)
    if method == "sigmoid":
        out = model.predict_proba(x.reshape(-1, 1))[:, 1]
    else:
        out = model.predict(x)
    return _np.clip(np.asarray(out, dtype=float), 0.0, 1.0)


def _split_calfit_select(cal: pd.DataFrame) -> tuple:
    """Earlier inner-val races -> fit; later races -> selection (temporal)."""
    races = list(dict.fromkeys(cal["race_id"].astype(str)))
    if len(races) < 2:
        raise ExperimentConfigError("calibration needs >= 2 races")
    cut = max(1, len(races) // 2)
    fit_races, sel_races = set(races[:cut]), set(races[cut:])
    return (cal[cal["race_id"].isin(fit_races)].reset_index(drop=True),
            cal[cal["race_id"].isin(sel_races)].reset_index(drop=True))


def select_calibration(cal: pd.DataFrame) -> dict:
    """Part I: RAW/SIGMOID/ISOTONIC on TRAIN-history evidence only.

    Calibrators fit on earlier inner-val races, judged on later ones:
    calibrated wins iff LL gain > 1e-4 AND no Brier harm. Deterministic;
    ties prefer RAW > SIGMOID > ISOTONIC. Winners refit on the FULL
    calibration set before outer application.
    """
    from raceintel.model_lab.metrics import brier, binary_logloss
    calfit, calselect = _split_calfit_select(cal)
    y_sel = calselect["target"].to_numpy(dtype=float)
    p_raw = calselect["probability"].to_numpy(dtype=float)
    ll_raw = float(binary_logloss(y_sel, p_raw))
    brier_raw = float(brier(y_sel, p_raw))
    support, fitted, outcome = {}, {}, {"RAW": {
        "ll": ll_raw, "brier": brier_raw, "status": "REFERENCE"}}
    for method in ("sigmoid", "isotonic"):
        audit = support_audit(calfit, method)
        support[method] = audit
        if audit["status"] != "OK":
            outcome[method] = {"status": audit["status"]}
            continue
        calibrator = (fit_platt if method == "sigmoid" else fit_isotonic)(
            calfit["probability"].to_numpy(dtype=float),
            calfit["target"].to_numpy(dtype=float))
        fitted[method] = calibrator
        p_cal = apply_calibrator(
            calibrator, calselect["probability"].to_numpy(dtype=float))
        outcome[method] = {
            "status": "EVALUATED",
            "ll": float(binary_logloss(y_sel, p_cal)),
            "brier": float(brier(y_sel, p_cal)),
            "ll_gain_vs_raw": float(ll_raw - binary_logloss(y_sel, p_cal)),
            "brier_gap_vs_raw": float(brier(y_sel, p_cal) - brier_raw)}
    selected, reason = "RAW", "no calibrated variant beat RAW beyond 1e-4 " \
        "without Brier harm on train-history selection races"
    for method in ("sigmoid", "isotonic"):
        node = outcome[method]
        if node.get("status") != "EVALUATED":
            continue
        if node["ll_gain_vs_raw"] > CAL_LL_MARGIN \
                and node["brier_gap_vs_raw"] <= 1e-12:
            if selected == "RAW" or node["ll_gain_vs_raw"] > outcome[
                    selected]["ll_gain_vs_raw"]:
                # ties keep earlier (simpler) method: strict improvement only
                selected, reason = method, \
                    f"LL gain {node['ll_gain_vs_raw']:.6f} > 1e-4, no Brier " \
                    f"harm ({node['brier_gap_vs_raw']:.3e}) on selection races"
    final_calibrator = None
    if selected != "RAW":
        # Refit the winning method on the FULL calibration set (history).
        final_calibrator = (fit_platt if selected == "sigmoid"
                            else fit_isotonic)(
            cal["probability"].to_numpy(dtype=float),
            cal["target"].to_numpy(dtype=float))
    return {"selected_method": selected, "reason": reason,
            "support": support, "outcome": outcome,
            "calfit_races": int(calfit["race_id"].nunique()),
            "calselect_races": int(calselect["race_id"].nunique()),
            "final_calibrator": final_calibrator}

# ---------------------------------------------------------------------------
# Nested refinement runner (Part J): inner selection -> calibration recipe
# (train-history only) -> outer refit -> RAW + CALIBRATED outer predictions.
# ---------------------------------------------------------------------------

def run_d_fold(augmented: DATA.CanonicalMatrix,
               plain: DATA.CanonicalMatrix, family: str, outer_fold: str,
               feature_names: tuple) -> dict:
    """One D family-fold: select refined config, calibrate, predict outer."""
    from raceintel.model_lab import runner as RUN
    from raceintel.model_lab import stages as STAGES
    from raceintel.model_lab import v3_dynamics_experiment as V3C

    require_d_family(family)
    H.verify_contracts()
    H.assert_development_fold(outer_fold)
    grid = d_grids()[family]
    resolved = TASKS.resolve_task(H.TASK)
    schema = DATA.feature_schema(augmented.frame, list(feature_names))
    timings: dict = {}
    with TIMING.Timer() as total:
        # -- inner evaluation over the frozen D grid ---------------------
        with TIMING.Timer() as t:
            inner_splits = INNER.resolve_inner_splits(outer_fold)
        timings["inner_resolve_seconds"] = t.seconds
        scores: dict = {s.inner_fold_id: {} for s in inner_splits}
        stored_preds: dict = {}
        estimator_fits = 0
        inner_seconds = 0.0
        for split in inner_splits:
            for season in (*split.train_seasons, *split.validation_seasons):
                if int(season) == 2025:
                    raise ProtectedHoldoutError("2025 in D inner folds")
            frame_tr = augmented.select_seasons(split.train_seasons)
            frame_va = augmented.select_seasons(split.validation_seasons)
            _, y_tr, _ = SPLITS._apply_mask(frame_tr, resolved)
            _, y_va, meta_va = SPLITS._apply_mask(frame_va, resolved)
            X_tr = frame_tr.loc[y_tr.index, list(feature_names)].copy()
            X_va = frame_va.loc[y_va.index, list(feature_names)].copy()
            with TIMING.Timer() as t:
                pre = PRE.fit_preprocessor(X_tr, schema)
                Z_tr, Z_va = pre.transform(X_tr), pre.transform(X_va)
            inner_seconds += t.seconds
            yv = np.asarray(y_va.astype(float))
            races = np.asarray(meta_va["race_id"].astype(str))
            seasons = np.asarray(meta_va["season"].astype(int))
            y_tr_arr = np.asarray(y_tr.astype(float))
            for cfg in grid:
                key = d_config_id(family, cfg)
                with TIMING.Timer() as t:
                    est = build_d_estimator(family, cfg)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        est.fit(Z_tr, y_tr_arr)
                estimator_fits += 1
                inner_seconds += t.seconds
                proba = np.asarray(est.predict_proba(Z_va))[
                    :, H._positive_index(est)]
                value = AGG.race_macro(yv, proba, races, "log_loss")["value"]
                scores[split.inner_fold_id][key] = float(value)
                stored_preds.setdefault(key, []).append(pd.DataFrame({
                    "probability": proba, "target": yv, "race_id": races,
                    "season": seasons,
                    "inner_fold": split.inner_fold_id}))
            del Z_tr, Z_va, pre
        timings["inner_seconds"] = inner_seconds
        # -- selection (mean inner LL, frozen tie rule) ------------------
        aggregates = {}
        for cfg in grid:
            key = d_config_id(family, cfg)
            values = {name: scores[name][key] for name in scores}
            aggregates[key] = {"config": {k: v for k, v in cfg.items()
                                          if not k.startswith("_")},
                               **AGG.aggregate_folds(values)}
        defined = {k: v for k, v in aggregates.items()
                   if v.get("mean") is not None and np.isfinite(v["mean"])}
        if not defined:
            raise ExperimentConfigError(f"{family}/{outer_fold}: no finite D")
        best = min(v["mean"] for v in defined.values())
        within = [k for k, v in defined.items()
                  if v["mean"] <= best + H.TIE_TOLERANCE]
        by_key = {d_config_id(family, c): c for c in grid}
        chosen = min(within,
                     key=lambda k: d_complexity_rank(family, by_key[k]))
        selection = {"selected_key": chosen,
                     "selected_config": aggregates[chosen]["config"],
                     "selected_mean": defined[chosen]["mean"],
                     "best_mean": best,
                     "within_tolerance": sorted(within),
                     "tie_break_applied": len(within) > 1}
        # -- calibration recipe on selected config's history preds -------
        cal = pd.concat(stored_preds[chosen], ignore_index=True).sort_values(
            ["season", "race_id"], kind="mergesort").reset_index(drop=True)
        with TIMING.Timer() as t:
            cal_selection = select_calibration(cal)
        timings["calibration_seconds"] = t.seconds
        # -- outer refit + single validation prediction ------------------
        with TIMING.Timer() as t:
            res = H.run_outer(augmented, plain, outer_fold, family,
                              selection["selected_config"],
                              feature_arm=H.ARM_PRIMARY,
                              feature_names=tuple(feature_names))
        timings["outer_seconds"] = t.seconds
        p_raw = np.asarray(res["predictions"], dtype=float)
        method = cal_selection["selected_method"]
        if method == "RAW":
            p_cal = p_raw
        else:
            p_cal = apply_calibrator(cal_selection["final_calibrator"], p_raw)
        frame_raw = H.build_oof_frame(res, outer_fold, H.ARM_PRIMARY)
        frame_raw["model_config_id"] = \
            f"D-refined:{selection['selected_key']}"
        frame_cal = frame_raw.copy()
        frame_cal["probability"] = p_cal
        frame_cal["model_config_id"] = \
            f"D-calibrated:{selection['selected_key']}:{method}"
    timings["total_seconds"] = total.seconds
    # Note: frame identity columns shared; probability columns differ only
    # when a calibrator was selected (else calibrated == RAW, method=RAW).
    return {"family": family, "outer_fold": outer_fold,
            "selection": selection, "aggregates": aggregates,
            "scores": scores, "estimator_fits": estimator_fits,
            "calibration_selection": {k: v for k, v in
                                      cal_selection.items()
                                      if k != "final_calibrator"},
            "calibration_method": method,
            "outer": res, "frame_raw": frame_raw, "frame_calibrated": frame_cal,
            "timings": timings}
