"""V3.5B dataset + target + coherence tests. No fitting, no 2025 contact."""
import glob
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import outcomes as OC
from raceintel.model_lab.errors import ProtectedHoldoutError

ROOT = Path(__file__).resolve().parents[1]
A_EXPECT = "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
DS_ID = "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
FEAT_HASH = "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"


def manifest():
    return json.loads(
        (ROOT / "results/v3/v3_5b/dataset_manifest.json").read_text())


def sidecar():
    return pd.read_parquet(
        ROOT / "data/v3/v3_5b/outcome_targets_2018_2024.parquet")


def test_a_contract_sha_exact():
    c = json.loads(
        (ROOT / "results/v3/v3_5a/experiment_contract.json").read_text())
    blob = json.dumps({k: v for k, v in c.items() if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        c["contract_hash"] == A_EXPECT


def test_a_task_exact():
    c = json.loads(
        (ROOT / "results/v3/v3_5a/experiment_contract.json").read_text())
    assert c["selected_primary_task"] == "ordered_cumulative_finish_thresholds"


def test_development_seasons_exact():
    assert OC.ALLOWED_SEASONS == (2018, 2019, 2020, 2021, 2022, 2023, 2024)
    with pytest.raises(ProtectedHoldoutError):
        OC.assert_development_seasons([2024, 2025])
    with pytest.raises(ProtectedHoldoutError):
        OC.load_development_labels([2025])


def test_2025_contact_none():
    assert manifest()["2025_status"].startswith("NONE")


def test_threshold_order_exact():
    assert OC.THRESHOLD_ORDER == (1, 3, 5, 10)
    assert OC.TARGET_NAMES == ("is_top1", "is_top3", "is_top5", "is_top10")
    assert OC.TARGET_ALIASES == {"is_top1": "p_win", "is_top3": "p_podium",
                                 "is_top5": "p_top5", "is_top10": "p_top10"}


def test_outcome_grain_unique():
    sc = sidecar()
    assert sc[["race_id", "driver_id"]].drop_duplicates().shape[0] <= len(sc)
    m = manifest()
    assert m["outcome_rows"] == 2979 and m["races"] == 149


def test_state_identity_unique():
    sc = sidecar()
    assert sc["state_id"].is_unique
    assert len(sc) == 162728 == manifest()["state_rows"]


def test_state_target_alignment_exact():
    from raceintel.config import V2Paths
    mat = pd.read_parquet(
        "data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet",
        columns=["state_id", "race_id", "season", "driver_id"])
    mat = mat[mat["season"].isin([2018, 2019, 2020, 2021, 2022, 2023, 2024])]
    sc = sidecar()
    assert set(sc["state_id"].astype(str)) == \
        set(mat["state_id"].astype(str))
    key = sc.set_index("state_id")[["race_id", "driver_id"]].astype(str)
    ref = mat.set_index("state_id")[["race_id", "driver_id"]].astype(str)
    assert (key == ref.loc[key.index]).all().all()


def test_permutation_invariance():
    sc = sidecar()
    sh = sc.sample(frac=1.0, random_state=7)
    assert set(sh["state_id"]) == set(sc["state_id"])
    a = sc.set_index("state_id").sort_index()[list(OC.TARGET_NAMES)]
    b = sh.set_index("state_id").sort_index()[list(OC.TARGET_NAMES)]
    assert (a.values == b.values).all()


def test_target_values_binary():
    sc = sidecar()
    for name in OC.TARGET_NAMES:
        assert set(np.unique(sc[name].to_numpy())) <= {0, 1}, name


def test_label_nesting_zero_violations():
    sc = sidecar()
    v = sc[list(OC.TARGET_NAMES)].to_numpy()
    assert int(((v[:, :-1] <= v[:, 1:]).all(axis=1) == False).sum()) == 0


def test_future_retirement_not_excluded():
    # 393 unclassified-tail OUTCOMES (outcome grain); their 9142 state rows
    # are present in the sidecar as structural threshold negatives.
    assert manifest()["semantic_counts"]["UNCLASSIFIED_TAIL"] == 393
    sc = sidecar()
    retired = sc[sc["outcome_semantic"] == "UNCLASSIFIED_TAIL"]
    assert len(retired) == 9142
    assert (retired[list(OC.TARGET_NAMES)].to_numpy() == 0).all()


def test_dns_no_state_behavior():
    # The 3 never-started withdrawals have no states (correctly absent from
    # the state sidecar); they exist only at outcome grain. The 76 zero-lap
    # result rows are the DNS/lap-1-exit population.
    sc = sidecar()
    assert (sc["outcome_semantic"] == "WITHDRAWN_NO_RESULT").sum() == 0
    assert manifest()["semantic_counts"]["WITHDRAWN_NO_RESULT"] == 3
    from raceintel.config import V2Paths
    p = V2Paths.resolve()
    zero_lap_outcomes = 0
    for s in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        files = glob.glob(str(p.processed_dir / "results" / f"season={s}"
                              / "*.parquet"))
        r = pd.concat([pd.read_parquet(f) for f in files])
        zero_lap_outcomes += int((r["laps_completed"] == 0).sum())
    assert zero_lap_outcomes == 76


def test_unclassified_tail_semantics():
    assert OC.SEM_UNCLASSIFIED_TAIL == "UNCLASSIFIED_TAIL"
    labels = OC.load_development_labels([2024])
    fr = OC.build_outcome_frame(labels)
    unc = fr[fr["outcome_semantic"] == "UNCLASSIFIED_TAIL"]
    assert len(unc) > 0
    assert (unc[list(OC.TARGET_NAMES)].to_numpy() == 0).all()


def test_classified_finisher_semantics():
    labels = OC.load_development_labels([2024])
    fr = OC.build_outcome_frame(labels)
    clf = fr[fr["outcome_semantic"] == "CLASSIFIED_POSITION"]
    assert len(clf) > 0
    assert int(clf["is_top1"].sum()) == 24
    assert int(clf["is_top3"].sum()) == 72


def test_classified_retirement_semantics():
    from raceintel.pipeline import d9 as D9
    from raceintel.config import V2Paths
    p = V2Paths.resolve()
    files = glob.glob(str(p.processed_dir / "results" / "season=2024"
                          / "*.parquet"))
    res = pd.concat([pd.read_parquet(f) for f in files])
    lab = D9.labels_from_results(res)
    fr = OC.build_outcome_frame(lab)
    assert (fr["outcome_semantic"] == "CLASSIFIED_POSITION").sum() == \
        int(lab["classified_flag"].sum())


def test_unknown_status_fail_closed():
    with pytest.raises(ValueError):
        OC.classify_outcome_row("Q", False, 20)
    with pytest.raises(ValueError):
        OC.classify_outcome_row("R", True, 18)


def test_field_size_independence():
    m = manifest()
    assert m["field_sizes"] == {"19": 1, "20": 148}
    assert m["non20_fields"] == {"2024-r03-R": 19}
    assert "20" not in json.dumps(OC.THRESHOLD_ORDER)


def test_110_feature_columns_exact():
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    assert len(names_110) == 110
    assert tuple(names_110[:84]) == names_84


def test_feature_identity_exact():
    assert manifest()["feature_identity"]["hash"] == FEAT_HASH
    assert manifest()["feature_identity"]["n"] == 110


def test_no_target_leakage():
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = V3C.v3_feature_names(
        V3C.ARM_B, tuple(canonical_predictive_names()))
    bad = set(names_110) & (set(OC.TARGET_NAMES) | {"outcome_semantic",
                                                    "position_final",
                                                    "classified_flag"})
    assert not bad


def test_no_status_metadata_leakage():
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = V3C.v3_feature_names(
        V3C.ARM_B, tuple(canonical_predictive_names()))
    assert "status_text" not in names_110 and "position_text" not in names_110


def test_no_spatial_features():
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = V3C.v3_feature_names(
        V3C.ARM_B, tuple(canonical_predictive_names()))
    assert not any("spatial" in c.lower() or c.startswith("p12_")
                   for c in names_110)


def test_projection_mathematical_examples():
    cases = [([0.1, 0.2, 0.4, 0.8], [0.1, 0.2, 0.4, 0.8]),
             ([0.2, 0.1, 0.4, 0.8], [0.15, 0.15, 0.4, 0.8]),
             ([0.5, 0.4, 0.3, 0.8], [0.4, 0.4, 0.4, 0.8]),
             ([0.8, 0.6, 0.4, 0.2], [0.5, 0.5, 0.5, 0.5]),
             ([0.3, 0.3, 0.3, 0.3], [0.3, 0.3, 0.3, 0.3]),
             ([0, 0, 0, 0], [0, 0, 0, 0]),
             ([1, 1, 1, 1], [1, 1, 1, 1])]
    for raw, exp in cases:
        q, _ = OC.project_isotonic(raw)
        assert np.allclose(q, exp, atol=1e-12), (raw, q)


def test_coherent_input_unchanged():
    q, d = OC.project_isotonic([0.05, 0.2, 0.5, 0.9])
    assert np.array_equal(q, [0.05, 0.2, 0.5, 0.9])
    assert d["n_violated_before"] == 0 and d["mean_abs_adjustment"] == 0.0


def test_projection_monotonic():
    rng = np.random.default_rng(3)
    mat = rng.random((500, 4))
    q, _ = OC.project_isotonic(mat)
    assert bool((np.diff(q, axis=1) >= 0).all())


def test_projection_bounded():
    q, _ = OC.project_isotonic([[0.0, 1.0, 0.0, 1.0]])
    assert bool(((q >= 0.0) & (q <= 1.0)).all())


def test_projection_deterministic():
    a, _ = OC.project_isotonic([0.6, 0.2, 0.7, 0.5])
    b, _ = OC.project_isotonic([0.6, 0.2, 0.7, 0.5])
    assert np.array_equal(a, b)


def test_projection_rejects_invalid_input():
    for bad in ([0.1, float("nan"), 0.3, 0.4], [0.1, float("inf"), 0.3, 0.4],
                [-0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 1.5], [0.1, 0.2, 0.3]):
        with pytest.raises(ValueError):
            OC.project_isotonic(bad)


def test_derived_bands_nonnegative():
    q, _ = OC.project_isotonic([[0.7, 0.2, 0.9, 0.85], [0.05, 0.2, 0.5, 0.9]])
    b = OC.derived_bands(q)
    assert bool((b >= 0).all())


def test_derived_bands_sum_to_one():
    rng = np.random.default_rng(5)
    mat = rng.random((200, 4))
    q, _ = OC.project_isotonic(mat)
    b = OC.derived_bands(q)
    assert np.allclose(b.sum(axis=1), 1.0, atol=1e-9)


def test_dataset_logical_identity_deterministic():
    assert manifest()["logical_identity"] == DS_ID


def test_rebuild_identity_exact():
    assert manifest()["physical_identity"]["path"] == \
        "data/v3/v3_5b/outcome_targets_2018_2024.parquet"


def test_harness_readiness_complete():
    h = json.loads(
        (ROOT / "results/v3/v3_5b/harness_readiness.json").read_text())
    assert h["all_pass"] is True
    assert h["dataset_identity"] == DS_ID
    assert all(h["checks"].values())


def test_no_model_fitted():
    mods = (ROOT / "raceintel/model_lab/outcomes.py").read_text()
    for token in ("LogisticRegression", ".fit(", "XGBClassifier",
                  "HistGradientBoosting", "IsotonicRegression"):
        assert token not in mods, token
    assert sorted(glob.glob("data/v3/v3_5b/*.parquet")) == \
        ["data/v3/v3_5b/outcome_targets_2018_2024.parquet"]


def test_no_learned_predictions():
    files = glob.glob("data/v3/v3_5b/*.parquet")
    assert sorted(files) == ["data/v3/v3_5b/outcome_targets_2018_2024.parquet"]
    sc = sidecar()
    assert set(sc.columns) == {"state_id", "race_id", "season", "driver_id",
                               "outcome_semantic", *set(OC.TARGET_NAMES)}


def test_no_serving_api_frontend_change():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True, cwd=ROOT).stdout
    for line in out.splitlines():
        p = line[3:]
        # V3.6F/G chartered Strategy 2.0 paths admitted; anything else
        # under api//frontend//model_lab/serving still fails.
        # V3.7H reconciliation: V3.7F/V3.7G chartered counterfactual paths
        # admitted (frozen science untouched).
        if p.startswith(("api/v2_strategy_v3_", "api/main.py",
                         "api/v2_counterfactual_",
                         "frontend/app/strategy/page.tsx",
                         "frontend/features/strategy/components/Strategy",
                         "frontend/features/strategy/hooks/useStrategy",
                         "frontend/features/strategy/lib/strategy",
                         "frontend/lib/v2.ts",
                         "frontend/app/counterfactuals",
                         "frontend/features/counterfactuals",
                         "frontend/components/shell/CommandBar.tsx")):
            continue
        assert not p.startswith(("api/", "frontend/", "raceintel/model_lab/serving")), line
