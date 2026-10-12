"""V3.8C trajectory tests: exact-state sequences, directional change,
missing-state honesty, stage/race-macro aggregation, undefined states.
"""

import json
from pathlib import Path

import pytest

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M
from raceintel.consensus import trajectories as T

ROOT = Path(__file__).resolve().parents[1]


def _rec(state_id, lap, stage, p_a, p_b, ra=None, rb=None,
         comparable=True, reason=None):
    return (state_id, lap, stage, p_a, p_b, ra, rb, comparable, reason)


def test_temporal_decreasing_gap():
    frames = (
        _rec("s1", 10, "EARLY", 0.3, 0.5, 2.0, 1.0),
        _rec("s2", 20, "MID", 0.35, 0.45, 2.0, 2.0),
        _rec("s3", 30, "LATE", 0.4, 0.42, 1.0, 1.0),
    )
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    assert [o.absolute_gap for o in obs] == pytest.approx([0.2, 0.1, 0.02])
    changes = T.directional_changes(obs)
    assert [c.direction_label for c in changes] == [
        "CONVERGING", "CONVERGING"]
    assert changes[0].delta_absolute_gap == pytest.approx(-0.1)


def test_temporal_increasing_gap():
    frames = (
        _rec("s1", 10, "EARLY", 0.4, 0.42, 1.0, 1.0),
        _rec("s2", 20, "MID", 0.35, 0.45, 2.0, 2.0),
    )
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    changes = T.directional_changes(obs)
    assert changes[0].direction_label == "DIVERGING"
    assert changes[0].delta_absolute_gap == pytest.approx(0.08)


def test_temporal_unchanged():
    frames = (
        _rec("s1", 10, "EARLY", 0.3, 0.5, 2.0, 1.0),
        _rec("s2", 20, "MID", 0.3, 0.5, 2.0, 1.0),
    )
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    changes = T.directional_changes(obs)
    assert changes[0].direction_label == "UNCHANGED"
    assert changes[0].delta_absolute_gap == 0.0


def test_temporal_missing_state_gap_preserved():
    frames = (
        _rec("s1", 10, "EARLY", 0.3, 0.5, 2.0, 1.0),
        _rec("s2", 15, "MID", 0.35, 0.45, 2.0, 2.0),
    )
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    changes = T.directional_changes(
        obs, missing_counts={("s1", "s2"): 4})
    assert changes[0].lap_delta == 5
    assert changes[0].missing_intermediate_states == 4


def test_no_interpolation_across_uncomparable():
    frames = (
        _rec("s1", 10, "EARLY", 0.3, 0.5, 2.0, 1.0),
        _rec("s2", 20, "MID", None, None, None, None, False,
             "SOURCE_UNAVAILABLE"),
        _rec("s3", 30, "LATE", 0.4, 0.42, 1.0, 1.0),
    )
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    assert obs[1].comparable is False
    assert obs[1].absolute_gap is None
    # No change spans the uncomparable observation.
    assert T.directional_changes(obs) == ()


def test_signed_gap_series_orientation():
    frames = (_rec("s1", 10, "EARLY", 0.2, 0.5, 3.0, 1.0),)
    obs = T.gap_series(frames, "perez", C.SourceId.V3_1B_LOGISTIC,
                       C.SourceId.MC2_E)
    assert obs[0].signed_gap == pytest.approx(0.3)
    assert obs[0].rank_displacement == pytest.approx(-2.0)


def test_stage_labels_reused():
    aggs = T.aggregate_by_stage(
        (("EARLY", "2022-r01-R", 0.2), ("MID", "2022-r01-R", 0.1),
         ("LATE", "2022-r01-R", 0.05), ("EARLY", "2023-r05-R", 0.3)))
    assert [a.stage for a in aggs] == ["EARLY", "MID", "LATE"]
    early = aggs[0]
    assert early.n_values == 2 and early.n_races == 2
    assert early.mean_value == pytest.approx(0.25)
    assert early.median_value == pytest.approx(0.25)


def test_stage_unknown_rejected():
    with pytest.raises(ValueError):
        T.aggregate_by_stage((("UNKNOWN", "2022-r01-R", 0.1),))


def test_race_macro_equal_weight_structure():
    aggs = T.aggregate_race_macro(
        (("2022-r01-R", 0.2), ("2022-r01-R", 0.1),
         ("2023-r05-R", 0.3)))
    assert [a.race_id for a in aggs] == ["2022-r01-R", "2023-r05-R"]
    assert aggs[0].mean_value == pytest.approx(0.15)
    assert aggs[0].n_states == 2


def test_undefined_reasons_cover_contract():
    names = {r.value for r in M.UndefinedReason}
    contract = json.loads(
        (ROOT / "results" / "v3" / "v3_8c" / "metrics_contract.json")
        .read_text())
    assert names == set(contract["undefined_metric_semantics"])


def test_trajectories_implementation_identity():
    assert T.TRAJECTORIES_IMPLEMENTATION_IDENTITY == \
        "v3.8c-consensus-trajectories-v1"


def test_machine_epsilon_differences_preserved():
    assert M.signed_gap(0.3, 0.3 + 1e-12) == pytest.approx(1e-12)
    assert M.absolute_gap(0.3, 0.3 + 1e-12) > 0.0


def test_multi_source_summary_has_no_consensus_scalar():
    import raceintel.consensus.trajectories as tra
    lines = [ln for ln in open(tra.__file__).read().splitlines()
             if "raceintel.consensus" not in ln]
    blob = "\n".join(lines).lower().replace(
        "v3.8c-consensus-trajectories-v1", "")
    for token in ("consensus leader", "consensus score",
                  "consensus =", "majority", "chosen leader",
                  "combined"):
        assert token not in blob, token
