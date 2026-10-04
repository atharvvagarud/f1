"""V3.1B artifact tests (corpus-dependent; Tier-3 only).

Builds the full 2018-2025 sidecar once per session into a temp dir and
validates schema, join integrity, determinism, provenance, coverage, and
firewalls. Listed in scripts/ci_corpus_dependent.txt; never runs in
normal source CI. Contains NO model performance evaluation.
"""

import json

import pytest

from raceintel.features.dynamics import build as B
from raceintel.features.dynamics import contract as C
from raceintel.features.dynamics import validation as V


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("v3_dyn")
    result = B.build(out_dir=str(out))
    import pandas as pd
    sidecar = pd.read_parquet(result["sidecar"])
    return result, sidecar


def test_row_count_and_identity_unique(built):
    result, sidecar = built
    V.check_row_identity(sidecar)
    assert result["provenance_record"]["row_count"] == 189420


def test_schema_dtypes_order(built):
    _, sidecar = built
    names = list(C.feature_set_names("all"))
    V.check_frame_schema(sidecar, names)
    V.check_values(sidecar, names)
    assert [c for c in sidecar.columns
            if c != "state_id"] == names


def test_join_integrity_both_directions(built):
    from raceintel.config import V2Paths
    from raceintel.features import build_matrix as F15
    _, sidecar = built
    matrix, _ = F15.load_matrix(V2Paths.resolve())
    mkeys = set(matrix["state_id"].astype(str))
    skeys = set(sidecar["state_id"].astype(str))
    assert mkeys == skeys
    assert len(sidecar) == len(matrix) == 189420


def test_provenance_complete_and_pinned(built):
    result, _ = built
    prov = result["provenance_record"]
    assert prov["contract_version"] == "v3.1a-v2"
    assert prov["contract_sha"] == C.contract_hash()
    assert prov["parent_content_sha"] == V.EXPECTED_PARENT_CONTENT
    assert prov["parent_parquet_sha"] == V.EXPECTED_PARENT_PARQUET
    assert prov["feature_count"] == 29
    assert prov["label_blind"] is True
    assert len(prov["season_coverage"]) == 8
    on_disk = json.loads(open(result["provenance"]).read())
    assert on_disk["logical_content_sha"] == prov["logical_content_sha"]


def test_determinism_rebuild(built):
    import pandas as pd
    result, sidecar = built
    again = pd.read_parquet(result["sidecar"])
    assert B.content_hash(again) == result["provenance_record"][
        "logical_content_sha"]
    assert B.content_hash(sidecar) == B.content_hash(again)


def test_season_and_stage_coverage(built):
    from raceintel.config import V2Paths
    from raceintel.features import build_matrix as F15
    _, sidecar = built
    matrix, _ = F15.load_matrix(V2Paths.resolve())
    cov = matrix[["state_id", "season",
                  "race_progress_frac"]].copy()
    cov["state_id"] = cov["state_id"].astype(str)
    frame = sidecar.merge(cov, on="state_id", validate="one_to_one")
    report = {}
    for season, sub in frame.groupby("season"):
        frac = {n: float(sub[n].notna().mean())
                for n in C.feature_set_names("all")}
        report[int(season)] = frac
        # every season has finite follower levels (no season-proxy collapse)
        assert frac["dyn_follower_gap_last_seconds"] > 0.5, season
        assert frac["dyn_follower_lap_diff"] > 0.5, season
        assert frac["dyn_field_spread_lap"] > 0.8, season
    stages = {
        "EARLY": frame[frame["race_progress_frac"] < 1.0 / 3.0],
        "MID": frame[(frame["race_progress_frac"] >= 1.0 / 3.0)
                     & (frame["race_progress_frac"] < 2.0 / 3.0)],
        "LATE": frame[frame["race_progress_frac"] >= 2.0 / 3.0],
    }
    for name, sub in stages.items():
        assert len(sub) > 60000, name
        # slopes thin out early (honest missingness), never vanish late
        assert float(sub["dyn_gap_leader_slope_l3"].notna().mean()) > 0.3, \
            name


def test_missingness_and_distribution_sanity(built):
    _, sidecar = built
    names = list(C.feature_set_names("all"))
    for n in names:
        col = sidecar[n]
        assert not bool((col == float("inf")).any()) if \
            str(col.dtype) == "float64" else True
    finite_frac = {n: float(sidecar[n].notna().mean()) for n in names}
    # depths/counts always defined; slopes mostly defined; volatility thin
    assert finite_frac["dyn_hist_laps_available"] == 1.0
    assert finite_frac["dyn_gap_n_l10_leader"] == 1.0
    assert finite_frac["dyn_gap_leader_slope_l3"] > 0.5
    assert finite_frac["dyn_follower_gap_last_seconds"] > 0.5
    assert finite_frac["dyn_follower_gap_slope_l5"] > 0.3
    desc = sidecar[names].describe()
    assert bool((desc.loc["max"] > desc.loc["min"]).all())
