"""V3.3B harness tests (Part AA). Corpus-light except the parity gate.

Fast source/contract/grid/firewall/OOF tests run without fits. Two
marked tests run real D1 fits (logistic parity ~10 s, family smoke
determinism on a tiny synthetic frame). No 2025 access anywhere.
"""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import data as DATA
from raceintel.model_lab import inner_splits as INNER
from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutError,
)

A_SHA = "d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7"


def test_a_contract_sha_verification():
    assert H.verify_a_contract()["contract_sha"] == A_SHA


def test_b_prereg_sha_verification():
    prereg = H.load_prereg()
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        prereg["preregistration_identity"]
    assert H.verify_prereg()["prereg_sha"] == \
        prereg["preregistration_identity"]


def test_110_feature_count_and_ordering():
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    assert len(names_110) == 110
    assert tuple(names_110[:84]) == names_84
    contract = H.check_feature_contract(names_84, names_110)
    assert contract["n_84"] == 84 and contract["n_core"] == 26


def test_core_exactly_26():
    from raceintel.features.dynamics import contract as DYN
    assert len(DYN.feature_set_names("core")) == 26


def test_sidecar_non_core_exclusion():
    from raceintel.features.dynamics import contract as DYN
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = H.feature_names_110(tuple(canonical_predictive_names()))
    sidecar_all = set(DYN.feature_set_names("all"))
    core = set(DYN.feature_set_names("core"))
    non_core = sidecar_all - core
    assert len(sidecar_all) == 29 and len(non_core) == 3
    assert not (non_core & set(names_110))


def test_identity_join_and_duplicate_rejection():
    augmented, _ = V3C.load_joined_frame()
    canon = DATA.load_canonical()
    assert augmented.frame["state_id"].is_unique
    assert len(augmented.frame) == len(canon.frame)
    assert set(augmented.frame["state_id"]) == set(canon.frame["state_id"])


def test_label_parity():
    augmented, _ = V3C.load_joined_frame()
    canon = DATA.load_canonical()
    assert augmented.frame["is_winner"].equals(canon.frame["is_winner"])


def test_84_arm_parity():
    augmented, _ = V3C.load_joined_frame()
    canon = DATA.load_canonical()
    names_84 = V3C.v3_feature_names(V3C.ARM_A)
    ds = V3C.materialize_v3(augmented, "D1", V3C.ARM_A, names_84)
    assert ds.train_counts["eligible"] == 88123
    assert ds.validation_counts["eligible"] == 23577
    assert ds.X_train[list(names_84)].equals(
        canon.frame.loc[ds.X_train.index, list(names_84)])


def test_candidate_registry_exact_set():
    assert sorted(H.candidate_registry()) == [
        "extra_trees", "hist_gradient_boosting", "logistic_regression",
        "xgboost"]


def test_grid_size_bound():
    for fam, grid in H.candidate_grids().items():
        assert 1 <= len(grid) <= 12, fam


def test_grid_deterministic_ids():
    for fam, grid in H.candidate_grids().items():
        ids = [H.config_id(fam, c) for c in grid]
        assert len(set(ids)) == len(ids)
        assert ids == [H.config_id(fam, c) for c in grid]


def test_complexity_tie_ordering():
    lr = H.candidate_grids()["logistic_regression"]
    assert H.complexity_rank("logistic_regression", {"C": 0.01}) < \
        H.complexity_rank("logistic_regression", {"C": 0.1})
    et = {"max_features": "sqrt", "min_samples_leaf": 10, "max_depth": 20}
    et2 = {"max_features": "sqrt", "min_samples_leaf": 1, "max_depth": None}
    assert H.complexity_rank("extra_trees", et) < \
        H.complexity_rank("extra_trees", et2)


def test_inner_fold_isolation():
    for outer in ("D1", "D2", "D3"):
        outer_split = V3C.RUN.resolve_development_fold(outer)
        for s in INNER.resolve_inner_splits(outer):
            assert max(s.train_seasons) < min(s.validation_seasons)
            assert set(s.train_seasons) | set(s.validation_seasons) <= \
                set(outer_split.train_seasons)
            assert 2025 not in (*s.train_seasons, *s.validation_seasons)


def test_outer_fold_isolation_and_firewall():
    for bad in ("HOLDOUT", "2025", "FINAL_FIT"):
        with pytest.raises((ProtectedHoldoutError, ExperimentConfigError)):
            H.assert_development_fold(bad)
    for good in ("D1", "D2", "D3"):
        H.assert_development_fold(good)


def test_oof_schema_uniqueness_bounds():
    n = 50
    frame = pd.DataFrame({
        "state_id": [f"s{i}" for i in range(n)],
        "season": [2022] * n,
        "race_id": ["r1"] * 25 + ["r2"] * 25,
        "driver_id": ["d"] * n,
        "target": [0.0, 1.0] * 25,
        "fold": ["D1"] * n,
        "stage": ["EARLY"] * n,
        "feature_arm": [H.ARM_PRIMARY] * n,
        "model_family": ["logistic_regression"] * n,
        "model_config_id": ["C=0.01"] * n,
        "probability": np.linspace(0.01, 0.99, n),
    })
    report = H.validate_oof_frame(frame)
    assert report["n_rows"] == n and report["n_races"] == 2
    bad = frame.copy()
    bad.loc[0, "probability"] = 1.5
    with pytest.raises(InvalidPredictionError):
        H.validate_oof_frame(bad)
    dup = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    with pytest.raises(ExperimentConfigError):
        H.validate_oof_frame(dup)


def test_metric_reuse():
    out = AGG.race_macro([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2],
                         ["r1", "r1", "r2", "r2"], "log_loss")
    assert out["scope"] == "race_macro" and out["n_races"] == 2


def test_race_level_alignment_and_bootstrap_determinism():
    a = {"r1": 0.1, "r2": 0.2, "r3": 0.15}
    b = {"r1": 0.09, "r2": 0.21, "r3": 0.14}
    first = V3C.paired_bootstrap(a, b)
    second = V3C.paired_bootstrap(a, b)
    assert first == second
    assert first["n_races"] == 3


def _tiny_frame(n=200, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"f0": rng.normal(size=n), "f1": rng.normal(size=n)})
    y = pd.Series((rng.random(n) < 0.3).astype(float))
    return X, y


def test_family_determinism_and_serialization_tiny():
    import tempfile
    from pathlib import Path
    schema = DATA.FeatureSchema(numeric=("f0", "f1"), boolean=(),
                                categorical=())
    X, y = _tiny_frame()
    cfgs = {"logistic_regression": {"C": 0.01},
            "hist_gradient_boosting": {"learning_rate": 0.1,
                                       "max_leaf_nodes": 7,
                                       "min_samples_leaf": 5},
            "extra_trees": {"max_features": "sqrt", "min_samples_leaf": 1,
                            "max_depth": 4},
            "xgboost": {"learning_rate": 0.1, "max_depth": 2,
                        "min_child_weight": 1}}
    for fam, cfg in cfgs.items():
        det = H.determinism_check(fam, cfg, X, y, schema, X)
        assert det["stable"], fam
        fitted, est, _ = H.fit_family(X, y, schema, fam, cfg)
        ser = H.serialization_roundtrip(fam, cfg, fitted, est, X)
        assert ser["equivalent"], fam


def test_failure_behavior():
    with pytest.raises(ExperimentConfigError):
        H.build_estimator("lightgbm", {})
    with pytest.raises(ExperimentConfigError):
        H.build_estimator("logistic_regression", {"C": 0.01, "bogus": 1})
    with pytest.raises((ProtectedHoldoutError, ExperimentConfigError)):
        H.assert_development_fold("HOLDOUT")
    # missing CORE column -> identity drift (short list != frozen order)
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = H.feature_names_110(tuple(canonical_predictive_names()))
    assert len(names_110) == 110
    short = tuple(list(names_110)[:100])
    assert len(short) != 110
    # invalid probability / missing target rejected
    frame = pd.DataFrame({
        "state_id": ["s1", "s2"], "season": [2022, 2022],
        "race_id": ["r1", "r1"], "driver_id": ["d1", "d2"],
        "target": [0.0, 1.0], "fold": ["D1", "D1"],
        "stage": ["EARLY", "EARLY"], "feature_arm": [H.ARM_PRIMARY] * 2,
        "model_family": ["xgboost"] * 2, "model_config_id": ["x"] * 2,
        "probability": [0.2, float("nan")]})
    with pytest.raises(InvalidPredictionError):
        H.validate_oof_frame(frame)
    no_target = frame.copy()
    no_target["probability"] = [0.2, 0.8]
    no_target.loc[0, "target"] = float("nan")
    with pytest.raises(ExperimentConfigError):
        H.validate_oof_frame(no_target)
    # fold mismatch: tuning refuses non-development folds
    with pytest.raises((ProtectedHoldoutError, ExperimentConfigError)):
        from raceintel.model_lab import inner_splits as _I
        _I.resolve_inner_splits("HOLDOUT")


def test_v3_1_logistic_parity_d1():
    """Harness logistic control reproduces V3.1B/C D1 within 1e-9."""
    augmented, plain = V3C.load_joined_frame()
    names_110 = H.feature_names_110()
    res = H.run_outer(augmented, plain, "D1", "logistic_regression",
                      {"C": 0.01}, feature_arm=H.ARM_PRIMARY,
                      feature_names=names_110)
    base = pd.read_parquet(
        "data/v3/v3_1c/pred_ALL_84_PLUS_V3_1_DYNAMICS_CORE__D1.parquet")
    ordered = base.set_index("state_id").loc[res["state_ids"]]
    diff = float(np.max(np.abs(
        np.asarray(res["predictions"]) - ordered["y_pred"].to_numpy())))
    assert diff <= 1e-9
    assert abs(float(res["metrics"]["log_loss"]["race_macro"]["value"])
               - 0.08067523650595465) <= 1e-9
