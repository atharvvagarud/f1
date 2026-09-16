"""M1 tests: experiment framework + temporal evaluation infrastructure.

Fast, focused coverage of the canonical loader, feature/task resolution,
temporal splits, holdout guard, dataset materialization, prediction
semantics/alignment, metrics, calibration, stages, aggregation, baselines,
experiment identity/serialization and the static guards. No candidate
estimator is trained and no 2025 target performance is computed.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from v2.config import V2Paths
from v2.features.build_matrix import content_hash, output_dir
from v2.model_lab import aggregation as AGG
from v2.model_lab import baselines as B
from v2.model_lab import calibration as CAL
from v2.model_lab import data as D
from v2.model_lab import errors as E
from v2.model_lab import experiment as EX
from v2.model_lab import metrics as M
from v2.model_lab import predictions as PR
from v2.model_lab import results as RES
from v2.model_lab import splits as S
from v2.model_lab import stages as ST
from v2.model_lab import tasks as T
from v2.model_lab import timing as TM
from v2.model_lab.protocol import (
    EXPECTED_MATRIX_CONTENT_HASH,
    MODEL_LAB_PROTOCOL_VERSION,
    PROTECTED_HOLDOUT_SEASON,
)
from v2.model_lab.winner import synchronized_winner_top_k

ROOT = Path(__file__).resolve().parents[1]
_OUT = output_dir(V2Paths.resolve())
_HAS_ARTIFACT = (_OUT / "manifest.json").exists()

pytestmark = pytest.mark.skipif(
    not _HAS_ARTIFACT, reason="canonical F15 matrix artifact not present")


@pytest.fixture(scope="session")
def canonical():
    return D.load_canonical(verify_content_hash=True)


@pytest.fixture(scope="session")
def fold_summaries(canonical):
    return {fold: S.materialize(canonical, "winner", fold, "ALL_84").summary()
            for fold in ("D1", "D2", "D3")}


def _tiny_canonical(frame):
    return D.CanonicalMatrix(None, frame, {})


# --- matrix loader + feature/task resolution ------------------------------

def test_loader_versions_and_hash(canonical):
    assert canonical.manifest["matrix_version"] == "v1"
    assert canonical.manifest["feature_set_version"] == "v8"
    assert canonical.manifest["label_set_version"] == "v1"
    assert len(canonical.predictive_columns) == 84
    assert len(canonical.label_columns) == 7
    assert canonical.manifest["content_hash"] == EXPECTED_MATRIX_CONTENT_HASH


def test_loader_content_hash_matches(canonical):
    assert content_hash(canonical.frame) == EXPECTED_MATRIX_CONTENT_HASH


def test_loader_canonical_order(canonical):
    key = ["season", "round_no", "race_id", "state_time_s", "lap_number",
           "driver_id"]
    ids = canonical.frame["state_id"].reset_index(drop=True)
    sorted_ids = (canonical.frame.sort_values(key, kind="mergesort")
                  ["state_id"].reset_index(drop=True))
    assert ids.equals(sorted_ids)


def test_feature_schema_dtypes(canonical):
    schema = canonical.schema
    assert len(schema.numeric) + len(schema.boolean) \
        + len(schema.categorical) == 84
    assert set(schema.categorical) == {"compound", "stint_compound",
                                       "track_state"}
    assert schema.kind_of("position") == "numeric"
    assert schema.kind_of("flag_red") == "boolean"
    assert schema.to_dict()["counts"]["categorical"] == 3


def test_feature_set_resolution(canonical):
    assert D.resolve_features("ALL_84", canonical) \
        == canonical.predictive_columns
    assert len(D.resolve_features("CURRENT_ORDER_ONLY", canonical)) == 1
    assert len(D.resolve_features("MINIMAL_RACE_STATE", canonical)) == 3
    cumulative = [n for n in D.resolve_features(
        "CUMULATIVE_07_INTERACTIONS", canonical)]
    assert cumulative == list(canonical.predictive_columns)
    logo = D.resolve_features("ALL_MINUS_INTERACTIONS", canonical)
    assert len(logo) == 84 - 3
    with pytest.raises(E.UnknownFeatureSetError):
        D.resolve_features("NOT_A_SET", canonical)


def test_feature_frame_order(canonical):
    frame = D.feature_frame(canonical, "CURRENT_ORDER_ONLY")
    assert list(frame.columns) == ["position"]


def test_task_masks_and_dnf(canonical):
    totals = S.validate_task_masks(canonical)
    assert totals["winner"] == 189420
    assert totals["final_position"] == 178963
    assert totals["gain"] == totals["loss"] == totals["position_change"] \
        == 189126
    winner = T.resolve_task("winner")
    assert winner.label_column == "is_winner"
    assert winner.eligibility_mask == "eligible_is_winner"
    assert winner.probability_semantics == "INDEPENDENT_BINARY"
    assert T.resolve_task("final_position").is_ordinal
    with pytest.raises(E.UnknownTaskError):
        T.resolve_task("dnf")
    with pytest.raises(E.UnknownTaskError):
        T.resolve_task("nope")


# --- splits + holdout guard -----------------------------------------------

def test_split_definitions():
    assert S.get_split("D1").train_seasons == (2018, 2019, 2020, 2021)
    assert S.get_split("D1").validation_seasons == (2022,)
    assert S.get_split("D2").validation_seasons == (2023,)
    assert S.get_split("D3").validation_seasons == (2024,)
    final = S.get_split("FINAL_FIT")
    assert final.train_seasons == tuple(range(2018, 2025))
    assert final.validation_seasons == ()
    assert final.is_final_fit


def test_split_counts_match_m0(canonical, fold_summaries):
    assert S.M0_FOLD_STATE_COUNTS["D1"] == (88123, 23577)
    got = {fold: (s["train"]["states"], s["validation"]["states"])
           for fold, s in fold_summaries.items()}
    assert got == S.M0_FOLD_STATE_COUNTS
    for fold, summary in fold_summaries.items():
        train_exp, train_pos = S.M0_FOLD_TASK_COUNTS[fold]["train"]["winner"]
        assert summary["train"]["eligible"] == train_exp
        assert summary["train"]["positives"] == train_pos
        vtrain, vval = S.M0_FOLD_TASK_COUNTS[fold]["validation"]["winner"]
        assert summary["validation"]["eligible"] == vtrain
        assert summary["validation"]["positives"] == vval


def test_split_no_overlap_and_chronology(canonical):
    for fold in ("D1", "D2", "D3"):
        split = S.get_split(fold)
        S.validate_split(canonical, split)
        train, val = S.split_frame(canonical, split)
        assert not (set(train["race_id"]) & set(val["race_id"]))
        assert int(train["season"].max()) < int(val["season"].min())


def test_2025_absent_from_development():
    for fold in ("D1", "D2", "D3"):
        split = S.get_split(fold)
        assert PROTECTED_HOLDOUT_SEASON not in split.train_seasons
        assert PROTECTED_HOLDOUT_SEASON not in split.validation_seasons


def test_final_fit_has_no_validation(canonical):
    ds = S.materialize(canonical, "winner", "FINAL_FIT", "ALL_84",
                       assert_m0_counts=False)
    assert ds.train_counts["states"] == 162728
    assert ds.validation_counts["states"] == 0
    assert len(ds.y_validation) == 0


def test_holdout_guard(canonical):
    with pytest.raises(E.ProtectedHoldoutError):
        S.get_split("HOLDOUT")
    split = S.get_split("HOLDOUT", allow_protected_holdout=True)
    assert split.validation_seasons == (2025,)
    S.validate_split(canonical, split)
    ds = S.materialize(canonical, "winner", "HOLDOUT", "ALL_84",
                       allow_protected_holdout=True, assert_m0_counts=False)
    assert ds.validation_counts["states"] == 26692
    assert ds.validation_counts["eligible"] == 26692


def test_unknown_fold_rejected():
    for bad in ("2025", "D4", "test", ""):
        with pytest.raises(E.UnknownFoldError):
            S.get_split(bad)


# --- dataset materialization ----------------------------------------------

def test_materialize_contract(canonical):
    ds = S.materialize(canonical, "winner", "D1", "ALL_84")
    assert ds.feature_names == canonical.predictive_columns
    assert list(ds.X_train.columns) == list(canonical.predictive_columns)
    for col in ("state_id", "race_id", "season", "round_no", "driver_id",
                "lap_number", "state_time_s"):
        assert col in ds.train_metadata.columns


def test_materialize_masks_before_selection(canonical):
    ds = S.materialize(canonical, "final_position", "D1", "ALL_84")
    assert ds.train_counts["eligible"] < ds.train_counts["states"]
    assert ds.y_train.notna().all()
    assert (ds.y_train > 0).all()


def test_materialize_position_change_uses_gain_loss_mask(canonical):
    ds = S.materialize(canonical, "position_change", "D1", "ALL_84")
    assert ds.train_counts["eligible"] == S.M0_FOLD_TASK_COUNTS["D1"]["train"][
        "position_change"][0]


def test_source_not_mutated(canonical):
    S.materialize(canonical, "winner", "D2", "MINIMAL_RACE_STATE")
    assert content_hash(canonical.frame) == EXPECTED_MATRIX_CONTENT_HASH


# --- metrics ---------------------------------------------------------------

def test_binary_probability_metrics():
    y = [1, 0]
    p = [0.5, 0.5]
    assert M.binary_logloss(y, p) == pytest.approx(np.log(2))
    assert M.brier(y, p) == pytest.approx(0.25)
    assert M.roc_auc([1, 0], [0.9, 0.1]) == pytest.approx(1.0)
    assert M.roc_auc([1, 0], [0.1, 0.9]) == pytest.approx(0.0)
    assert M.pr_auc([0, 1], [0.6, 0.4]) == pytest.approx(0.5)


def test_perfect_and_constant_predictions():
    y = [1, 1, 0, 0]
    assert M.binary_logloss(y, y) < 1e-6
    assert M.brier(y, y) == pytest.approx(0.0)
    assert M.brier(y, [0.5] * 4) == pytest.approx(0.25)


def test_single_class_slices():
    assert M.roc_auc([1, 1, 1], [0.5, 0.6, 0.7]) is None
    assert M.roc_auc([0, 0], [0.5, 0.6]) is None
    assert M.pr_auc([0, 0], [0.5, 0.6]) is None
    assert M.spearman([1, 1, 1], [1, 2, 3]) is None


def test_invalid_probabilities_rejected():
    with pytest.raises(E.InvalidPredictionError):
        M.binary_logloss([1, 0], [1.5, 0.5])
    with pytest.raises(E.InvalidPredictionError):
        M.brier([1, 0], [np.nan, 0.5])
    with pytest.raises(E.InvalidPredictionError):
        M.binary_logloss([1, 2], [0.5, 0.5])
    # ranking metrics accept scores outside [0, 1] but not NaN/inf
    assert M.roc_auc([1, 0], [5.0, -3.0]) == pytest.approx(1.0)
    with pytest.raises(E.InvalidPredictionError):
        M.roc_auc([1, 0], [np.inf, 0.0])


def test_ordinal_regression_metrics():
    assert M.mae([1, 2], [1.5, 2.5]) == pytest.approx(0.5)
    assert M.rmse([1, 2], [1.5, 2.5]) == pytest.approx(0.5)
    assert M.spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert M.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)


def test_compute_metric_dispatch():
    assert M.compute_metric("brier", [1, 0], [0.5, 0.5]) == pytest.approx(0.25)
    with pytest.raises(E.UnsupportedMetricError):
        M.compute_metric("accuracy", [1, 0], [0.5, 0.5])


# --- calibration -----------------------------------------------------------

def test_reliability_bins_and_ece():
    y = [0, 0, 1, 1]
    p = [0.1, 0.4, 0.35, 0.8]
    bins = CAL.reliability_bins(y, p, n_bins=10)
    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == 4
    assert CAL.expected_calibration_error(y, p, n_bins=10) == pytest.approx(
        0.3375)
    report = CAL.calibration_report(y, p)
    assert report["n_bins"] == 10 and report["binning"] == "equal_width"


# --- stages ----------------------------------------------------------------

def test_stage_boundaries():
    values = [0.0, 1.0 / 3.0 - 1e-9, 1.0 / 3.0, 2.0 / 3.0 - 1e-9,
              2.0 / 3.0, 1.0]
    labels = list(ST.stage_partition(np.array(values)))
    assert labels == ["EARLY", "EARLY", "MID", "MID", "LATE", "LATE"]
    with pytest.raises(ValueError):
        ST.stage_partition(np.array([1.5]))
    with pytest.raises(ValueError):
        ST.stage_partition(np.array([np.nan]))


# --- aggregation -----------------------------------------------------------

def test_race_macro_vs_state_pooled():
    y = [1, 1, 0, 0]
    p = [1.0, 0.0, 0.0, 0.0]
    races = ["A", "B", "B", "B"]
    scoped = AGG.scoped_metric(y, p, races, "brier")
    assert scoped["race_macro"]["value"] == pytest.approx((0.0 + 1.0 / 3) / 2)
    assert scoped["state_pooled"]["value"] == pytest.approx(0.25)
    assert scoped["race_macro"]["value"] != scoped["state_pooled"]["value"]
    assert scoped["race_macro"]["scope"] == "race_macro"
    assert scoped["state_pooled"]["scope"] == "state_pooled"


def test_fold_aggregation():
    agg = AGG.aggregate_folds({"D1": 0.1, "D2": 0.2, "D3": 0.3})
    assert agg["mean"] == pytest.approx(0.2)
    assert agg["std"] == pytest.approx(0.1)
    assert agg["n_folds"] == 3 and agg["per_fold"]["D2"] == 0.2


def test_stage_scoped_metrics():
    y = [1, 0, 1, 0]
    p = [0.9, 0.1, 0.8, 0.2]
    races = ["A", "A", "B", "B"]
    stages = ["EARLY", "EARLY", "LATE", "LATE"]
    out = AGG.stage_scoped_metrics(stages, y, p, races, "brier")
    assert set(out) == {"EARLY", "MID", "LATE"}
    assert out["MID"]["n_states"] == 0
    assert out["EARLY"]["race_macro"]["n_races"] == 1


# --- prediction semantics + alignment --------------------------------------

def test_prediction_semantics():
    with pytest.raises(E.InvalidPredictionError):
        PR.PredictionResult(kind=PR.PredictionKind.BINARY_PROBABILITY,
                            state_ids=("a",), values=np.array([0.5]))
    race = PR.PredictionResult(
        kind=PR.PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION,
        state_ids=("a", "b"), values=np.array([0.7, 0.3]),
        semantics=PR.ProbabilitySemantics.MUTUALLY_EXCLUSIVE_RACE,
        race_ids=("r", "r"))
    assert race.is_probability
    independent = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY, state_ids=("a", "b"),
        values=np.array([0.7, 0.5]),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)
    with pytest.raises(E.InvalidPredictionError):
        PR.require_race_distribution(independent)
    PR.require_race_distribution(race)


def test_prediction_alignment():
    pred = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=("b", "a"), values=np.array([0.2, 0.9]),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)
    assert list(PR.align(pred, ["a", "b"])) == [0.9, 0.2]
    with pytest.raises(E.PredictionAlignmentError):
        PR.align(pred, ["a", "a"])
    with pytest.raises(E.PredictionAlignmentError):
        PR.align(pred, ["a", "c"])
    extra = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=("a", "b"), values=np.array([0.5, 0.5]),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)
    with pytest.raises(E.PredictionAlignmentError):
        PR.align(extra, ["a"])


# --- baselines -------------------------------------------------------------

def _base_frame():
    return pd.DataFrame({
        "state_id": ["s1", "s2", "s3"],
        "position": [1, 2, 3],
        "grid_position": [2, 1, 3],
        "representative_recent_pace_s": [90.0, 89.0, 91.0],
    })


def test_current_leader_and_grid_pole():
    frame = _base_frame()
    _, val = B.run_baseline("CURRENT_LEADER", "winner", frame, frame)
    assert list(val.values) == [1.0, 0.0, 0.0]
    _, val = B.run_baseline("GRID_POLE", "winner", frame, frame)
    assert list(val.values) == [0.0, 1.0, 0.0]
    _, val = B.run_baseline("GRID_POLE", "final_position", frame, frame)
    assert val.kind is PR.PredictionKind.ORDINAL_PREDICTION
    assert list(val.values) == [2.0, 1.0, 3.0]


def test_class_prior_train_only():
    frame = _base_frame()
    train_y = pd.Series([1, 0, 0, 0])
    _, val = B.run_baseline("CLASS_PRIOR", "winner", frame, frame,
                            train_y=train_y)
    assert list(val.values) == [0.25, 0.25, 0.25]
    with pytest.raises(E.ExperimentConfigError):
        B.run_baseline("CLASS_PRIOR", "winner", frame, frame)


def test_recent_pace_uses_only_pace():
    frame = _base_frame()
    _, val = B.run_baseline("RECENT_PACE", "winner", frame, frame)
    assert val.kind is PR.PredictionKind.RANKING_SCORE
    assert list(val.values) == [-90.0, -89.0, -91.0]


def test_baseline_unsupported_task():
    frame = _base_frame()
    with pytest.raises(E.ExperimentConfigError):
        B.run_baseline("CURRENT_LEADER", "final_position", frame, frame)
    with pytest.raises(E.UnknownBaselineError):
        B.get_baseline("NOPE")


# --- experiment identity / config / results --------------------------------

def _config(**over):
    base = dict(task="winner", feature_set="ALL_84", fold="D1",
                model_family="logistic_regression", seed=42)
    base.update(over)
    return EX.build_config(**base)


def test_experiment_id_deterministic():
    assert _config().experiment_id == _config().experiment_id
    assert _config(seed=42).experiment_id != _config(seed=43).experiment_id
    assert _config(fold="D1").experiment_id != _config(fold="D2").experiment_id
    assert _config(model_parameters={"C": 1.0}).experiment_id != \
        _config(model_parameters={"C": 2.0}).experiment_id


def test_experiment_id_ignores_environment():
    a = _config(git_commit="aaa")
    b = _config(git_commit="bbb")
    assert a.experiment_id == b.experiment_id


def test_project_seed_helper():
    assert EX.PROJECT_SEED == 42
    assert EX.set_project_seed() == 42
    with pytest.raises(E.ExperimentConfigError):
        EX.set_project_seed(-1)


def test_config_validation():
    cfg = _config()
    cfg.validate()
    with pytest.raises(E.ExperimentConfigError):
        EX.build_config(task="winner", feature_set="ALL_84", fold="2025",
                        model_family="logistic_regression", seed=42)
    with pytest.raises(E.ExperimentConfigError):
        _config(matrix_content_hash="0" * 64).validate()
    with pytest.raises(E.ExperimentConfigError):
        _config(protocol_version="v9").validate()


def test_result_roundtrip_and_schema(tmp_path):
    cfg = _config()
    result = EX.ExperimentResult(
        experiment_id=cfg.experiment_id, status=EX.ExperimentStatus.SMOKE_TEST,
        warnings=["fixture"])
    dest = RES.write_experiment(cfg, result, root=tmp_path)
    assert not list(dest.glob("*.tmp"))
    read_cfg, read_result = RES.read_experiment(dest)
    assert read_cfg.experiment_id == cfg.experiment_id
    assert read_result.status is EX.ExperimentStatus.SMOKE_TEST
    bad = json.loads((dest / "result.json").read_text())
    bad["schema_version"] = "v99"
    (dest / "result.json").write_text(json.dumps(bad))
    with pytest.raises(E.ResultSchemaError):
        RES.read_experiment(dest)


def test_environment_metadata():
    env = RES.environment_metadata(ROOT)
    for key in ("python_version", "platform", "machine", "git_commit",
                "git_dirty"):
        assert key in env


def test_timing_and_latency_summary():
    with TM.Timer() as timer:
        pass
    assert timer.seconds >= 0
    _, samples = TM.timed_call(lambda: 1, repeats=3, warmup=1)
    assert len(samples) == 3
    summary = TM.latency_summary([1.0, 2.0, 3.0, 4.0])
    assert summary["count"] == 4
    assert summary["p50"] == pytest.approx(2.5)
    assert summary["min"] == 1.0 and summary["max"] == 4.0
    assert TM.latency_summary([])["count"] == 0


# --- winner synchronized top-k ---------------------------------------------

def test_synchronized_winner_top_k():
    rows = []
    for time_s, lap in [(10.0, 1), (20.0, 2)]:
        for driver, winner in (("a", True), ("b", False)):
            rows.append({
                "state_id": f"r|{driver}|{lap}", "race_id": "r",
                "season": 2020, "driver_id": driver, "lap_number": lap,
                "state_time_s": time_s, "is_winner": winner})
    frame = pd.DataFrame(rows)
    canonical = _tiny_canonical(frame)
    predictions = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(frame["state_id"]),
        values=np.array([0.9, 0.1, 0.8, 0.2]),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)
    out = synchronized_winner_top_k(predictions, canonical, top_k=(1, 3))
    assert out["accuracy"]["top1"] == pytest.approx(1.0)
    assert out["accuracy"]["top3"] == pytest.approx(1.0)
    assert out["n_evaluation_states"] == 4


# --- static guards ---------------------------------------------------------

# M3 scope note: M3 intentionally introduces the single permitted estimator
# (LogisticRegression reference) and M4 the two permitted nonlinear
# candidates (HistGradientBoosting, XGBoost) in the stage-owned modules below.
# Those files are excluded from this M1-era guard; the M3/M4 test modules own
# the stricter successor guards (only LogisticRegression / only the declared
# M4 families may train). The random-split guard above keeps scanning every
# module, including stage-owned files.
M3_OWNED_MODULES = frozenset({
    "preprocessing.py", "logreg.py", "model_runner.py", "model_suite.py",
    "run_models.py",
    # M4 stage-owned modules (HistGradientBoosting + XGBoost); the M4 test
    # module owns the stricter successor guard forbidding every other family.
    "tree_candidates.py", "nonlinear_runner.py", "nonlinear_suite.py",
    "run_nonlinear.py",
    # M5 stage-owned modules (ExtraTrees + RandomForest); the M5 test module
    # owns the stricter successor guard forbidding every other family.
    "bagged_candidates.py", "bagged_runner.py", "bagged_suite.py",
    "run_bagged.py",
    # M6 stage-owned modules (LogReg + ExtraTrees tuning); the M6 test module
    # owns the stricter successor guard forbidding every other family.
    "inner_splits.py", "tuning.py", "tuning_candidates.py",
    "tuning_runner.py", "tuning_suite.py", "run_tuning.py",
    # M7 stage-owned module (LogReg boundary resolution); the M7 test module
    # owns the stricter successor guard.
    "logreg_boundary.py", "run_boundary.py",
    # M8 stage-owned modules (Platt + isotonic calibration evaluation); the M8
    # test module owns the stricter successor guard.
    "calibration_selection.py", "run_calibration.py",
    # M9 stage-owned modules (final LogReg fit + one-shot protected holdout);
    # the M9 test module owns the stricter successor guard.
    "final_fit.py", "run_final.py",
    # P3.1 production-owned module (frozen inference only); the P3.1 test
    # module owns the stricter successor guard (no .fit(, no holdout access).
    "serving.py",
})


def _model_lab_sources():
    return sorted((ROOT / "v2" / "model_lab").glob("*.py"))


def test_no_random_split_patterns():
    forbidden = ("train_test_" + "split(", "KF" + "old(", "Shuffle" + "Split(")
    for path in _model_lab_sources():
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name}: forbidden {token!r}"


def test_no_candidate_estimator_construction():
    forbidden = ("LogisticReg" + "ression", "HistGradient" + "Boosting",
                 "XGB" + "Classifier", "LGBM" + "Classifier",
                 "CatBoost" + "Classifier", "RandomForest" + "Classifier",
                 "ExtraTrees" + "Classifier", "MLP" + "Classifier",
                 "import " + "torch", "from " + "torch")
    for path in _model_lab_sources():
        if path.name in M3_OWNED_MODULES:
            continue
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name}: forbidden {token!r}"
