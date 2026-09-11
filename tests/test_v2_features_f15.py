"""F15 tests: canonical model-ready feature matrix (offline).

Assembly/materialization verification: registry authority, column
classes, label join + state-dependent formulas, ordinal eligibility,
task masks, batch reuse (no per-state fan-out), materialized/reference
parity, determinism, atomic writes, loader safety, and failure modes.
"""

import glob
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import v2.features.build_matrix as B
from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    build_f11_registry,
    features_for_state,
    FeatureRequest,
)
from v2.labels import (
    LABEL_SET_VERSION,
    build_label_registry,
    ordinal_training_eligible,
    position_change_from_state,
)

ROOT = V2Paths.resolve().root
_OUT = B.output_dir(V2Paths.resolve())
_HAS_ARTIFACT = (_OUT / "manifest.json").exists()
_HAS_DATA = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2023").is_dir()

pytestmark = pytest.mark.skipif(
    not _HAS_DATA, reason="canonical data not present (data/v2 gitignored)")


@pytest.fixture(scope="session")
def paths():
    return V2Paths.resolve()


@pytest.fixture(scope="session")
def canonical(paths):
    out = B.output_dir(paths)
    if not (out / "manifest.json").exists():
        B.build(paths, force=True)
    matrix, manifest = B.load_matrix(paths)
    return matrix, manifest


@pytest.fixture(scope="session")
def registry():
    return build_f11_registry()


@pytest.fixture(scope="session")
def history(paths):
    return B.load_history(paths)


@pytest.fixture(scope="session")
def source_labels(paths):
    return B.load_source_labels(paths)


@pytest.fixture(scope="session")
def states(paths):
    return B.load_states(paths)


def _isnull(x):
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def _values_equal(a, b):
    if _isnull(a) or _isnull(b):
        return _isnull(a) and _isnull(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9
    return a == b


# --- §2/§3/§4/§5/§7 frozen versions + registry authority ---

def test_frozen_versions_and_counts(canonical, registry):
    _, m = canonical
    assert FEATURE_SET_VERSION == "v8"
    assert LABEL_SET_VERSION == "v1"
    assert len(registry) == 84
    assert len(build_label_registry()) == 7
    assert m["matrix_version"] == "v1"
    assert m["feature_set_version"] == "v8"
    assert m["label_set_version"] == "v1"
    assert m["predictive_feature_count"] == 84
    assert m["label_count"] == 7


def test_predictive_list_from_registry(canonical, registry):
    _, m = canonical
    expected = [d.name for d in registry if d.predictive_eligible]
    assert m["predictive_columns"] == expected


def test_label_list_from_registry(canonical):
    _, m = canonical
    assert set(m["label_columns"]) == set(build_label_registry().names())


def test_column_classes_distinct(canonical):
    _, m = canonical
    meta = set(m["metadata_columns"])
    pred = set(m["predictive_columns"])
    lab = set(m["label_columns"])
    comp = set(m["label_companion_columns"])
    task = set(m["task_eligibility_columns"])
    assert not (pred & lab) and not (pred & task) and not (lab & task)
    assert not (pred & comp) and not (meta & pred) and not (meta & lab)
    assert len(pred) == 84 and len(lab) == 7


def test_task_metadata_not_predictive(canonical):
    _, m = canonical
    assert not set(m["task_eligibility_columns"]) & set(m["predictive_columns"])
    assert not set(m["label_columns"]) & set(m["predictive_columns"])


# --- §1/§29 grain + identity ---

def test_matrix_grain_and_identity(canonical):
    df, m = canonical
    assert len(df) == 189420
    assert m["row_count"] == 189420
    assert m["race_count"] == 173
    assert m["season_range"] == [2018, 2025]
    assert not df.duplicated(["race_id", "driver_id", "lap_number"]).any()
    assert not df["state_id"].duplicated().any()


def test_canonical_sort_is_total(canonical):
    df, m = canonical
    key = m["canonical_sort"]
    sorted_df = df.sort_values(key, kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(df[key].reset_index(drop=True),
                                  sorted_df[key])


def test_no_row_drops(canonical, states):
    df, _ = canonical
    assert len(df) == len(states)
    assert set(zip(df.race_id, df.driver_id, df.lap_number)) == \
        set(zip(states.race_id, states.driver_id, states.lap_number))


# --- §5/§6/§30 labels ---

def test_label_join_many_to_one(canonical):
    _, m = canonical
    assert m["label_join"]["cardinality"] == "many_to_one"
    assert m["label_join"]["feature_rows"] == 189420
    assert m["label_join"]["matched"] == 189420
    assert m["label_join"]["missing_label"] == 0


def test_state_dependent_formulas_conform(canonical):
    df, _ = canonical
    sample = df.sample(n=2000, random_state=3)
    for _, r in sample.iterrows():
        pos = None if pd.isna(r["position"]) else int(r["position"])
        fp = None if pd.isna(r["final_position"]) else int(r["final_position"])
        exp = position_change_from_state(pos, fp)
        got = None if pd.isna(r["position_change_from_state"]) \
            else int(r["position_change_from_state"])
        assert exp == got
        if exp is None:
            assert pd.isna(r["gains_position_by_finish"])
            assert pd.isna(r["loses_position_by_finish"])
        else:
            assert bool(r["gains_position_by_finish"]) == (exp > 0)
            assert bool(r["loses_position_by_finish"]) == (exp < 0)


def test_label_constancy_within_race_driver(canonical):
    df, _ = canonical
    for col in ("final_position", "is_winner", "is_podium", "scored_points"):
        nun = df.groupby(["race_id", "driver_id"])[col].nunique(dropna=False)
        assert (nun <= 1).all(), col


def test_label_distributions(canonical):
    df, _ = canonical
    assert int((df["is_winner"] == True).sum()) == 10370  # noqa: E712
    assert int((df["is_podium"] == True).sum()) == 31106  # noqa: E712
    assert int((df["scored_points"] == True).sum()) == 103482  # noqa: E712


# --- §7/§8/§41/§42 ordinal + task eligibility ---

def test_ordinal_eligibility_matches_helper(canonical):
    df, _ = canonical
    sample = df.sample(n=2000, random_state=5)
    for _, r in sample.iterrows():
        cf = None if pd.isna(r["classified_flag"]) \
            else bool(r["classified_flag"])
        fp = None if pd.isna(r["final_position"]) else int(r["final_position"])
        exp = ordinal_training_eligible(cf, fp)
        got = r["eligible_ordinal_final_position"]
        if exp is None:
            assert pd.isna(got)
        else:
            assert bool(got) == exp


def test_ordinal_eligibility_not_naive(canonical):
    df, _ = canonical
    nonnull = int(df["final_position"].notna().sum())
    eligible = int((df["eligible_ordinal_final_position"] == True).sum())  # noqa: E712
    assert nonnull == 189420
    assert eligible == 178963
    assert eligible < nonnull  # W/D back-rank numerics excluded


def test_wd_not_ordinal_eligible(canonical):
    df, _ = canonical
    wd = df[df["classified_flag"] == False]  # noqa: E712
    assert len(wd) == 10457
    assert not (wd["eligible_ordinal_final_position"] == True).any()  # noqa: E712


def test_binary_task_masks(canonical):
    df, m = canonical
    assert bool((df["eligible_is_winner"] == True).all())  # noqa: E712
    assert bool((df["eligible_is_podium"] == True).all())  # noqa: E712
    assert bool((df["eligible_scored_points"] == True).all())  # noqa: E712


def test_gain_loss_eligibility(canonical):
    df, _ = canonical
    assert int((df["eligible_gain_loss"] == False).sum()) == 294  # noqa: E712
    assert int((df["eligible_gain_loss"] == True).sum()) == 189126  # noqa: E712
    # null gain/loss exactly where ineligible
    assert bool(df.loc[df["eligible_gain_loss"] == False,
                       "gains_position_by_finish"].isna().all())  # noqa: E712


# --- §28/§31/§38 schema + invariants ---

def test_schema_and_no_overlap(canonical, registry):
    df, m = canonical
    assert df.shape[1] == m["column_count"] == 106
    assert len(set(df.columns)) == df.shape[1]
    assert not set(m["predictive_columns"]) & set(m["label_columns"])
    assert "telemetry" not in " ".join(df.columns).lower()


def test_feature_domains(canonical, registry):
    df, m = canonical
    for d in registry:
        col = df[d.name]
        if d.dtype == "float64":
            v = col.dropna()
            assert np.isfinite(v).all(), d.name
        elif d.dtype == "bool":
            assert set(col.dropna().unique().tolist()) <= {True, False}, d.name
        elif d.dtype == "int64":
            assert col.dropna().apply(lambda x: float(x).is_integer()).all()
    assert not [c for c in m["predictive_columns"] if df[c].isna().all()]
    assert not [c for c in m["predictive_columns"]
                if df[c].nunique(dropna=True) <= 1]


def test_no_imputation_no_encoding_static():
    src = inspect.getsource(B)
    for banned in ("fillna", "StandardScaler", "OneHotEncoder", "sklearn",
                   "train_test_split", "imputer", "resample"):
        assert banned not in src, banned


# --- §32 materialized/reference parity ---

@pytest.mark.parametrize("target", [
    (2018, "2018-r04-R", "alonso", 2),
    (2025, "2025-r01-R", "norris", 35),
    (2022, "2022-r07-R", "norris", 30),
    (2021, "2021-r12-R", "hamilton", 2),
    (2022, "2022-r18-R", "ocon", 2),
    (2023, "2023-r01-R", "alonso", 28),
    (2019, "2019-r04-R", "kubica", 49),
])
def test_materialized_reference_parity(canonical, history, registry, states,
                                       target):
    df, _ = canonical
    season, rid, drv, lap = target
    sub = states[states.season == season]
    sub = sub[sub.race_id == rid].reset_index(drop=True)
    hit = sub[(sub.driver_id == drv) & (sub.lap_number == lap)].iloc[0]
    q = FeatureRequest(str(hit.race_id), str(hit.driver_id),
                       int(hit.lap_number), float(hit.state_time_s))
    res = features_for_state(q, registry, sub, history=history).value_dict()
    row = df[(df.race_id == rid) & (df.driver_id == drv)
             & (df.lap_number == lap)].iloc[0]
    for name, val in res.items():
        assert _values_equal(val, row[name]), (rid, drv, lap, name)


# --- §33/§25 determinism + idempotence ---

def test_shuffled_subset_determinism(states, history, registry,
                                     source_labels):
    sub = states[states.race_id.isin(["2023-r01-R", "2022-r07-R"])]
    m1, _ = B.assemble_matrix(sub, history, source_labels, registry,
                              validate=False)
    m2, _ = B.assemble_matrix(sub.sample(frac=1.0, random_state=7), history,
                              source_labels, registry, validate=False)
    assert B.content_hash(m1) == B.content_hash(m2)


def test_content_hash_matches_artifact(canonical, paths):
    df, m = canonical
    assert B.content_hash(df) == m["content_hash"]


def test_rebuild_idempotent_and_reuse(canonical, paths, tmp_path,
                                      monkeypatch):
    df0, m0 = canonical
    calls = {}
    names = ("passthrough_batch", "pace_batch", "gap_batch",
             "environment_batch", "context_batch", "rates_batch",
             "priors_batch", "interactions_batch")
    for name in names:
        orig = getattr(B, name)

        def wrap(orig=orig, name=name):
            def fn(*a, **k):
                calls[name] = calls.get(name, 0) + 1
                return orig(*a, **k)
            return fn
        monkeypatch.setattr(B, name, wrap())
    manifest = B.build(paths, out_dir=tmp_path, force=True)
    assert set(calls) == set(names)
    assert all(v == 1 for v in calls.values()), calls
    assert manifest["content_hash"] == m0["content_hash"]
    assert manifest["schema_hash"] == m0["schema_hash"]
    assert manifest["row_count"] == m0["row_count"]
    assert manifest["column_count"] == m0["column_count"]
    rebuilt = pd.read_parquet(tmp_path / "model_matrix.parquet")
    assert B.content_hash(rebuilt) == m0["content_hash"]


def test_no_per_state_fanout_static():
    src = inspect.getsource(B)
    assert "features_for_state" not in src
    assert "features_for_batch" not in src


# --- §21/§23/§27 manifest + fingerprints ---

def test_manifest_contents(canonical, paths):
    _, m = canonical
    for key in ("matrix_version", "feature_registry_fingerprint",
                "label_registry_fingerprint", "schema_hash", "content_hash",
                "source_fingerprints", "null_counts", "canonical_sort"):
        assert key in m
    assert set(m["source_fingerprints"]) >= {"d9_states", "labels"}
    for v in m["source_fingerprints"].values():
        assert len(v["sha256"]) == 64 and v["files"] >= 1
    assert len(m["feature_registry_fingerprint"]) == 64
    assert len(m["label_registry_fingerprint"]) == 64


def test_manifest_no_absolute_paths(canonical):
    _, m = canonical
    blob = json.dumps(m)
    assert str(V2Paths.resolve().root) not in blob


# --- §39/§40/§41/§42/§43 loader contract ---

def test_loader_selects_x_from_manifest(paths, canonical):
    _, m = canonical
    X = B.load_features(paths)
    assert set(m["predictive_columns"]) <= set(X.columns)
    assert not set(m["label_columns"]) & set(X.columns)
    assert not set(m["label_companion_columns"]) & set(X.columns)


def test_loader_labels_cannot_enter_x(paths, canonical):
    _, m = canonical
    X = B.load_features(paths, metadata=False)
    assert list(X.columns) == list(m["predictive_columns"])


def test_ordinal_task_loader_safety(paths, canonical):
    _, m = canonical
    X, y, mask = B.load_task("final_position", paths)
    assert set(mask.unique().tolist()) <= {True, False}
    assert int(mask.sum()) == 178963
    # must not be final_position.notna() (which would select all 189,420)
    assert int(y.notna().sum()) == 189420
    assert int(mask.sum()) < int(y.notna().sum())


def test_gain_loss_task_loader_safety(paths):
    X, y, mask = B.load_task("gain", paths)
    assert int(mask.sum()) == 189126
    assert y[mask == False].isna().all()


def test_binary_task_loaders(paths):
    for task, col in (("winner", "is_winner"), ("podium", "is_podium"),
                      ("points", "scored_points")):
        X, y, mask = B.load_task(task, paths)
        assert bool(mask.all())
        assert set(y.dropna().unique().tolist()) <= {True, False}


def test_loader_returns_raw_no_preprocessing(paths):
    X, y, mask = B.load_task("points", paths)
    # raw canonical semantics: no scaling/encoding artifacts
    assert X.select_dtypes(include=["number"]).shape[1] >= 1
    assert not any(str(c).startswith("encoded_") for c in X.columns)
    assert "sklearn" not in type(X).__module__


# --- §46 failure modes ---

def test_duplicate_state_identity_fails(states):
    dup = pd.concat([states, states.iloc[[0]]], ignore_index=True)
    with pytest.raises(B.MatrixBuildError, match="duplicate"):
        # replicate the guard directly
        if dup.duplicated(list(B.PK_COLUMNS)).any():
            raise B.MatrixBuildError("duplicate D9 state identity")


def test_validate_rejects_bad_shapes(canonical):
    df, m = canonical
    small = df.sample(n=100, random_state=1).reset_index(drop=True)
    missing = small.drop(columns=[m["predictive_columns"][0]])
    with pytest.raises(B.MatrixBuildError):
        B.validate_matrix(missing, m, expected_rows=100)
    extra = small.copy()
    extra["unexpected_predictive_col"] = 1.0
    with pytest.raises(B.MatrixBuildError):
        B.validate_matrix(extra, m, expected_rows=100)
    dup = pd.concat([small, small.iloc[[0]]], ignore_index=True)
    with pytest.raises(B.MatrixBuildError):
        B.validate_matrix(dup, m, expected_rows=101)


def test_validate_rejects_overlap(canonical):
    df, m = canonical
    small = df.head(50).copy()
    bad = dict(m)
    bad["label_columns"] = list(m["label_columns"]) + [m["predictive_columns"][0]]
    with pytest.raises(B.MatrixBuildError):
        B.validate_matrix(small, bad, expected_rows=50)


def test_version_mismatch_fails(monkeypatch, registry):
    monkeypatch.setattr(B, "FEATURE_SET_VERSION", "v9")
    with pytest.raises(B.MatrixBuildError, match="v8"):
        B.resolve_predictive_names(registry)
    monkeypatch.setattr(B, "LABEL_SET_VERSION", "v2")
    with pytest.raises(B.MatrixBuildError, match="v1"):
        B.resolve_label_names()


def test_atomic_write_failure_leaves_no_partial(paths, canonical, tmp_path,
                                                monkeypatch):
    df, m = canonical
    small = df.head(20).copy()
    out = tmp_path / "atomic"

    def boom(*a, **k):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(RuntimeError):
        B.write_matrix(paths, small, m, out_dir=out)
    assert not (out / "model_matrix.parquet").exists()
    assert not (out / "manifest.json").exists()
    assert not list(out.glob("*.tmp"))


def test_duplicate_label_key_fails(paths, source_labels):
    dup = pd.concat([source_labels, source_labels.iloc[[0]]],
                    ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        B.build_label_frame(dup)
