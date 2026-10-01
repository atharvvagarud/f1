"""F13 tests: canonical labels + target contracts (offline).

F13 creates NO predictive features. These tests pin: the frozen label
artifact audit, the separate v1 label registry, the v8/84 feature
freeze, factual target semantics, DNF/expected-finish rejection,
the state-dependent change specification, the F15 join contract,
and both mutation directions (features ignore labels; labels follow
results).
"""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import FEATURE_SET_VERSION, build_f11_registry
from raceintel.labels import (
    CANONICAL_LABEL_NAMES,
    LABEL_GRAIN,
    LABEL_SET_VERSION,
    LabelRegistry,
    build_label_frame,
    build_label_registry,
    gains_position_by_finish,
    join_labels_for_f15,
    loses_position_by_finish,
    position_change_from_state,
)

ROOT = V2Paths.resolve().root
_LABEL_GLOB = str(ROOT / "data/v2/processed/race_driver_labels"
                  "/*/*.parquet")
_HAS_LABELS = len(glob.glob(_LABEL_GLOB)) > 0
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()


def _labels():
    if not _HAS_LABELS:
        pytest.skip("canonical label data not present")
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        _LABEL_GLOB))], ignore_index=True)


@pytest.fixture()
def label_registry():
    return build_label_registry()


@pytest.fixture()
def feature_registry():
    return build_f11_registry()


# --- registry separation + freezes ---

def test_label_registry_separate_from_feature_registry(label_registry,
                                                       feature_registry):
    assert isinstance(label_registry, LabelRegistry)
    assert type(label_registry) is not type(feature_registry)
    assert len(label_registry) == 7
    assert len(feature_registry) == 84
    assert set(label_registry.names()) & set(feature_registry.names()) == set()
    assert FEATURE_SET_VERSION == "v8"
    assert LABEL_SET_VERSION == "v1"
    assert LABEL_GRAIN == ("race_id", "driver_id")


def test_no_dnf_no_expected_finish_labels(label_registry):
    names = " ".join(label_registry.names())
    for token in ("dnf", "retire", "reliab", "expected_finish", "success",
                  "performance", "win_probability", "telemetry"):
        assert token not in names, token


def test_feature_guard_rejects_canonical_label_names(feature_registry):
    from raceintel.features import FeatureDef, FeatureFamily, FeatureStatus
    from raceintel.features.contracts import (
        MinHistory, MinHistoryKind, MissingPolicy, SyncRequirement,
        TemporalRule,
    )
    from raceintel import contracts as C
    from raceintel.features.registry import validate_definition
    from raceintel.features import InvalidFeatureError
    for label_name in CANONICAL_LABEL_NAMES:
        with pytest.raises(InvalidFeatureError):
            validate_definition(FeatureDef(
                name=label_name, family=FeatureFamily.RACE_STATE, version=1,
                dtype="float64", unit="unitless", description="leak probe",
                sources=("driver_lap_state_d9.position",),
                formula_ref="probe", temporal_rule=TemporalRule.TARGET_STATE,
                sync=SyncRequirement.NONE,
                min_history=MinHistory(MinHistoryKind.NONE),
                missing=MissingPolicy.PRESERVE_SOURCE_NULL,
                availability=C.Availability.LAP_END,
                predictive_eligible=True, status=FeatureStatus.CANDIDATE))


def test_no_calculator_imports_labels():
    import raceintel.features as pkg
    from pathlib import Path
    bad = []
    for path in sorted(Path(pkg.__file__).parent.glob("*.py")):
        if path.name in ("registry.py", "__init__.py"):
            continue  # NAME guard (metadata) lives in registry by §22
        if path.name == "build_matrix.py":
            # F15 assembly layer is the one sanctioned label-consuming
            # module (feature/label join); it is not a predictive
            # calculator. Scoped out here, same as F14's calculator list.
            continue
        text = path.read_text()
        if "raceintel.labels" in text or "raceintel/labels" in text \
                or "race_driver_labels" in text:
            bad.append(path.name)
    assert bad == []


# --- artifact audit ---

def test_label_artifact_grain_and_uniqueness():
    df = _labels()
    assert len(df) == 3458
    assert df["race_id"].nunique() == 173
    assert int(df.duplicated(["race_id", "driver_id"]).sum()) == 0
    assert df["position_final"].isna().sum() == 3
    assert df["classified_position"].isna().sum() == 451
    assert df["points"].isna().sum() == 0


def _na_equal(a: pd.Series, b: pd.Series) -> bool:
    return bool((((a.fillna(False) == b.fillna(False))
                  & (a.isna() == b.isna())).all()))


def test_frozen_derivation_conformance():
    """Builder's documented formulas reproduce the frozen flags exactly."""
    df = _labels()
    pos = df["position_final"]
    assert _na_equal(pos.eq(1).where(pos.notna(), pd.NA), df["winner_flag"])
    assert _na_equal(pos.isin([1, 2, 3]).where(pos.notna(), pd.NA),
                     df["podium_flag"])
    assert (((df["points"].notna()) & (df["points"] > 0))
            == df["points_finish_flag"]).all()
    assert (df["classified_position"].notna()
            == df["classified_flag"]).all()


def test_winner_podium_cardinality():
    df = _labels()
    assert int((df["winner_flag"] == True).sum()) == 173  # noqa: E712
    assert int((df["podium_flag"] == True).sum()) == 519  # noqa: E712
    assert (df.groupby("race_id")["winner_flag"].sum() == 1).all()
    assert (df.groupby("race_id")["podium_flag"].sum() == 3).all()


def test_points_consistency_half_points():
    df = _labels()
    assert int((df["points_finish_flag"] == True).sum()) == 1730  # noqa: E712
    assert int(((df["points"] > 0)
                == df["points_finish_flag"]).sum()) == len(df)
    bel = df[df["race_id"] == "2021-r12-R"]
    assert len(bel) == 20
    assert bool(bel[bel["driver_id"] == "max_verstappen"]
                ["winner_flag"].iloc[0]) is True
    assert float(bel[bel["driver_id"] == "sainz"]["points"].iloc[0]) == 0.5
    assert bool(bel[bel["driver_id"] == "sainz"]
                ["points_finish_flag"].iloc[0]) is True
    jpn = df[df["race_id"] == "2022-r18-R"]
    assert int(jpn["winner_flag"].sum()) == 1


def test_status_tokens_preserved_verbatim():
    df = _labels()
    tokens = set(df["position_text"].dropna().unique())
    assert {"R", "W", "D"} <= tokens  # unclassified evidence kept, not parsed
    assert (df["position_text"].notna()).all()


def test_binary_ordinal_invariants():
    df = _labels()
    frame, _ = build_label_frame(df)
    for col in ("is_winner", "is_podium", "scored_points"):
        vals = set(frame[col].dropna().unique().tolist())
        assert vals <= {True, False}, (col, vals)
    pos = frame["final_position"].dropna()
    assert (pos > 0).all()
    assert not set(pos.unique().tolist()) & {-1, 999}
    assert np.isfinite(frame["scored_points"].astype(int)).all()


# --- builder ---

def test_build_label_frame_manifest():
    df = _labels()
    frame, manifest = build_label_frame(df)
    assert manifest["label_set_version"] == "v1"
    assert manifest["race_driver_rows"] == 3458
    assert manifest["races"] == 173
    assert manifest["winner_true"] == 173
    assert manifest["podium_true"] == 519
    assert manifest["points_true"] == 1730
    assert manifest["final_null"] == 3
    assert list(frame.columns[:2]) == ["race_id", "driver_id"]
    # deterministic rebuild
    frame2, manifest2 = build_label_frame(df)
    pd.testing.assert_frame_equal(frame, frame2)
    assert manifest == manifest2


def test_builder_rejects_duplicate_keys_and_bad_cardinality():
    df = _labels()
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        build_label_frame(dup)
    bad = df.copy()
    idx = bad[bad["winner_flag"] == True].index[:1]  # noqa: E712
    bad.loc[bad.index == bad.index[0], "winner_flag"] = True
    with pytest.raises(ValueError, match="cardinality"):
        build_label_frame(bad)


def test_stateless_participants_keep_labels():
    df = _labels()
    frame, _ = build_label_frame(df)
    stateless = [("2021-r22-R", "mazepin"),
                 ("2022-r02-R", "mick_schumacher"),
                 ("2022-r02-R", "tsunoda"),
                 ("2023-r15-R", "stroll"),
                 ("2023-r17-R", "sainz"),
                 ("2024-r21-R", "albon")]
    for race_id, driver_id in stateless:
        hit = frame[(frame["race_id"] == race_id)
                    & (frame["driver_id"] == driver_id)]
        assert len(hit) == 1  # label exists despite zero D9 states


def test_labels_respond_to_result_mutation():
    df = _labels()
    frame, _ = build_label_frame(df)
    mut = df.copy()
    row = mut[(mut["race_id"] == "2023-r01-R")
              & (mut["driver_id"] == "max_verstappen")].index[0]
    # winner -> P5, 25 pts -> 10 pts equivalent flip on source columns
    mut.loc[row, "position_final"] = 5
    mut.loc[row, "winner_flag"] = False
    mut.loc[row, "podium_flag"] = False
    frame2, _ = build_label_frame(mut)
    v0 = frame[(frame["race_id"] == "2023-r01-R")
               & (frame["driver_id"] == "max_verstappen")].iloc[0]
    v1 = frame2[(frame2["race_id"] == "2023-r01-R")
                & (frame2["driver_id"] == "max_verstappen")].iloc[0]
    assert bool(v0["is_winner"]) is True and bool(v1["is_winner"]) is False
    assert v1["final_position"] == 5


def test_future_race_isolation():
    df = _labels()
    frame, _ = build_label_frame(df)
    mut = df.copy()
    mut.loc[mut["race_id"] == "2025-r01-R", "winner_flag"] = False
    mut.loc[mut["race_id"] == "2025-r01-R", "position_final"] = 20
    frame2, _ = build_label_frame(mut)
    before = frame[frame["race_id"] == "2024-r01-R"].reset_index(drop=True)
    after = frame2[frame2["race_id"] == "2024-r01-R"].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)


def test_presentation_mutation_ignored():
    df = _labels()
    frame, _ = build_label_frame(df)
    mut = df.copy()
    mut["driver_abbreviation"] = "XXX"
    frame2, _ = build_label_frame(mut)
    pd.testing.assert_frame_equal(frame, frame2)


# --- state-dependent change specification ---

def test_position_change_formulas():
    assert position_change_from_state(5, 1) == 4
    assert position_change_from_state(1, 5) == -4
    assert position_change_from_state(3, 3) == 0
    assert position_change_from_state(None, 3) is None
    assert position_change_from_state(3, None) is None
    assert gains_position_by_finish(5, 1) is True
    assert gains_position_by_finish(3, 3) is False
    assert loses_position_by_finish(1, 5) is True
    assert loses_position_by_finish(3, 3) is False
    assert gains_position_by_finish(None, 1) is None


def test_conceptual_d9_coverage():
    if not (_HAS_LABELS and _HAS_D9):
        pytest.skip("canonical data not present")
    df = _labels()
    frame, _ = build_label_frame(df)
    cols = ["race_id", "driver_id", "position"]
    st = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(
        glob.glob(str(ROOT / "data/v2/processed/driver_lap_state_d9"
                       "/*/*.parquet")))], ignore_index=True)
    assert len(st) == 189420
    joined, report = join_labels_for_f15(st, frame)
    assert report["matched"] == 189420
    assert report["missing_label"] == 0
    assert len(joined) == len(st)
    assert int(joined["final_position"].isna().sum()) == 0
    change = joined["position"].astype("float") - \
        joined["final_position"].astype("float")
    assert int(change.notna().sum()) == 189126  # 294 position-null states


def test_f15_join_contract_fixture():
    states = pd.DataFrame({
        "race_id": ["r1", "r1", "r1", "r2"],
        "driver_id": ["a", "a", "b", "c"],
        "lap_number": [1, 2, 1, 1],
        "position": [3, 2, 1, 5],
    })
    labels = pd.DataFrame({
        "race_id": ["r1", "r1"],
        "driver_id": ["a", "b"],
        "is_winner": [False, True],
        "is_podium": [True, True],
        "scored_points": [True, True],
        "final_position": [2, 1],
    })
    out, report = join_labels_for_f15(states, labels)
    assert len(out) == 4  # row count preserved
    assert report == {"feature_rows": 4, "matched": 3, "missing_label": 1}
    assert (out[out["driver_id"] == "a"]["final_position"] == 2).all()
    assert out[out["driver_id"] == "c"]["final_position"].isna().all()


# --- §23 features ignore labels (real engine) ---

def test_features_ignore_label_mutation(feature_registry):
    if not (_HAS_LABELS and _HAS_D9):
        pytest.skip("canonical data not present")
    from raceintel.features import (
        FeatureRequest, PriorHistory, features_for_state, results_equal,
    )
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             "/season=2023/*.parquet")))], ignore_index=True)
    mk = lambda pat: pd.concat([pd.read_parquet(f) for f in sorted(
        glob.glob(str(ROOT / f"data/v2/processed/{pat}/season=*/*.parquet")))],
        ignore_index=True)
    h = PriorHistory(mk("hist_results"), mk("hist_races"), mk("results"),
                     mk("races"), mk("pit_stops"))
    sub = d9[d9["race_id"] == "2023-r01-R"]
    t = sub.iloc[500]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    base = features_for_state(q, feature_registry, sub, history=h)
    assert len(base.values) == 84
    # radical label mutation exists only in an in-memory copy the engine
    # never receives (no labels parameter exists on the engine path)
    labels = _labels()
    labels["winner_flag"] = False
    labels["position_final"] = 20
    labels["points"] = 0.0
    again = features_for_state(q, feature_registry, sub, history=h)
    assert results_equal(base, again)
