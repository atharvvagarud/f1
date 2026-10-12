"""V3.8B alignment tests: identity-safe frames + support accounting.

Proves exact state/driver alignment, metadata consistency, row-order
invariance, explicit missing-support semantics, target compatibility,
frame purity (no metrics, no ground truth), reproducibility, and the
nine fail-closed conditions.
"""

import json
from pathlib import Path

import pytest

from raceintel.consensus import adapters as A
from raceintel.consensus import alignment as L
from raceintel.consensus import contracts as C

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "results" / "v3" / "v3_8b" / "validation_corpus.json"


def _corpus():
    return json.loads(CORPUS.read_text())


def _prov(path="p", ident="i", model="m"):
    return C.Provenance(artifact_path=path, artifact_identity=ident,
                        model_identity=model)


def _rec(source, target, p, sid="s" * 64, drv="perez", stage="MID",
         lap=30, race="2022-r01-R", year=2022, round_=1):
    meta = A.StateMeta(driver_id=drv, race_id=race, year=year,
                       round=round_, lap=lap, stage=stage)
    fam = C.SOURCE_FAMILIES[source]
    return C.NativePrediction(
        state_id=sid, race_id=race, year=year, round=round_, lap=lap,
        stage=stage, driver_id=drv, source_id=source,
        source_family=fam, target=target,
        native_probability=A.validate_probability(p),
        normalization_semantics=C.SOURCE_NORMALIZATION[source],
        support_status=C.SupportStatus.AVAILABLE, support_reason=None,
        provenance=_prov())


def test_state_key_exact():
    rec = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.3)
    assert rec.key() == ("s" * 64, "perez")


def test_driver_key_exact():
    rec = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, drv="hamilton")
    assert rec.key() == ("s" * 64, "hamilton")


def test_state_mismatch_fails():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.3)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, sid="t" * 64)
    with pytest.raises(ValueError):
        L.align_pair("s" * 64, "perez", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


def test_driver_mismatch_fails():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.3)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, drv="hamilton")
    with pytest.raises(ValueError):
        L.align_pair("s" * 64, "perez", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


def test_metadata_contradiction_fails():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.3, lap=30)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, lap=31)
    with pytest.raises(ValueError):
        L.align_pair("s" * 64, "perez", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


def test_target_compatible_winner_pair():
    assert C.targets_compatible(
        C.SourceId.V3_1B_LOGISTIC, C.Target.WIN,
        C.SourceId.MC2_E, C.Target.WIN) is True
    assert C.targets_compatible(
        C.SourceId.V3_1B_LOGISTIC, C.Target.WIN,
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.WIN) is True
    assert C.targets_compatible(
        C.SourceId.V3_3_XGBOOST, C.Target.WIN,
        C.SourceId.MC2_E, C.Target.WIN) is True


def test_cross_target_incompatible():
    assert C.targets_compatible(
        C.SourceId.V3_1B_LOGISTIC, C.Target.WIN,
        C.SourceId.MC2_E, C.Target.TOP3) is False
    assert C.targets_compatible(
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.WIN,
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP5) is False
    assert C.targets_compatible(
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP3,
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP5) is False


def test_mc2_topk_gated_on_exposure():
    assert C.targets_compatible(
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP3,
        C.SourceId.MC2_E, C.Target.TOP3,
        mc2_targets=frozenset({C.Target.WIN, C.Target.TOP3})) is True
    assert C.targets_compatible(
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP3,
        C.SourceId.MC2_E, C.Target.TOP3,
        mc2_targets=frozenset({C.Target.WIN})) is False


def test_pair_frame_comparable_when_both_available():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.31)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.22)
    f = L.align_pair("s" * 64, "perez", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert f.pair_comparable is True
    assert f.target_compatible is True
    assert f.p_a_native == 0.31 and f.p_b_native == 0.22


def test_missing_source_explicit_not_dropped():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.31)
    f = L.align_pair("s" * 64, "perez", (a,),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert f.pair_comparable is False
    assert f.support_b is C.SupportStatus.UNAVAILABLE
    assert f.reason_b == "SOURCE_NOT_AVAILABLE"
    assert f.p_b_native is None


def test_missing_driver_explicit():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.31)
    f = L.align_pair("s" * 64, "perez", (a,),
                     C.SourceId.V3_1B_LOGISTIC,
                     C.SourceId.V3_5_LOGISTIC_CONTROL)
    assert f.support_b is C.SupportStatus.UNAVAILABLE


def test_row_order_permutation_invariant():
    corpus = _corpus()
    st = corpus["states"][1]
    sid = st["state_id"]
    kw = dict(race=st["race_id"], year=st["year"], round_=st["round"],
              lap=st["lap"], stage=st["stage"])
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.38, sid=sid,
             drv="verstappen", **kw)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.4, sid=sid,
             drv="verstappen", **kw)
    fwd = L.align_pair(sid, "verstappen", (a, b),
                       C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    rev = L.align_pair(sid, "verstappen", (b, a),
                       C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert fwd == rev


def test_driver_order_permutation_invariant():
    # Roster/record insertion order must not affect support accounting.
    def build(order):
        recs = {
            "verstappen": _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN,
                               0.4, drv="verstappen"),
            "perez": _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.2,
                          drv="perez"),
            "hamilton": _rec(C.SourceId.MC2_E, C.Target.WIN, 0.1,
                             drv="hamilton"),
        }
        return {"s" * 64: tuple(recs[d] for d in order)}
    acc1 = L.account_support(
        ("verstappen", "perez", "hamilton"),
        build(("verstappen", "perez", "hamilton")))
    acc2 = L.account_support(
        ("verstappen", "perez", "hamilton"),
        build(("hamilton", "perez", "verstappen")))
    assert acc1 == acc2


def test_positional_poison_rejected():
    # Same values, swapped identities: positional join would silently
    # cross drivers; identity join keeps them distinct.
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.4,
             drv="verstappen")
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, drv="perez")
    with pytest.raises(ValueError):
        L.align_pair("s" * 64, "verstappen", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


def test_comparison_frame_contains_no_metrics():
    assert C.frame_has_no_metrics_or_truth() is True
    names = set(C.comparison_frame_fields())
    assert "absolute_difference" not in names
    assert "rank" not in names
    assert "consensus" not in names


def test_comparison_frame_contains_no_ground_truth():
    names = set(C.comparison_frame_fields())
    for banned in ("actual_winner", "final_position", "observed_outcome",
                   "label", "y_true", "is_winner", "position_final"):
        assert banned not in names


def test_multi_source_frame_deterministic():
    a = _rec(C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.WIN, 0.3)
    b = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.31)
    c = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.22)
    m1 = L.align_multi("s" * 64, "perez", (a, b, c),
                       (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E,
                        C.SourceId.V3_5_LOGISTIC_CONTROL,
                        C.SourceId.V3_3_XGBOOST))
    m2 = L.align_multi("s" * 64, "perez", (c, a, b),
                       (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E,
                        C.SourceId.V3_5_LOGISTIC_CONTROL,
                        C.SourceId.V3_3_XGBOOST))
    assert m1 == m2
    assert [e["source_id"] for e in m1.entries] == sorted(
        [e["source_id"] for e in m1.entries], key=lambda s: s.value)
    assert [e["source_id"] for e in m1.excluded] == [
        C.SourceId.V3_3_XGBOOST]


def test_support_accounting_deterministic():
    acc = L.account_support(
        ("verstappen", "perez", "hamilton"),
        {"s" * 64: (
            _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.4,
                 drv="verstappen"),
            _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.2,
                 drv="perez"),
            _rec(C.SourceId.MC2_E, C.Target.WIN, 0.36,
                 drv="verstappen"))})
    assert acc.intersection == ("verstappen",)
    assert acc.candidate_drivers == ("verstappen", "perez", "hamilton")
    assert any(e["driver_id"] == "hamilton" for e in acc.exclusions)
    assert any(e["driver_id"] == "perez" and
               e["missing_from"] == ("MC2_E",) for e in acc.exclusions)


def test_ground_truth_fields_absent_from_frames():
    import dataclasses
    for cls in (C.ComparisonFrame, C.MultiSourceFrame,
                C.NativePrediction):
        names = {f.name for f in dataclasses.fields(cls)}
        for banned in C.FORBIDDEN_GROUND_TRUTH_FIELDS:
            assert banned not in names, (cls, banned)


def test_stage_single_canonical():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.3, stage="MID")
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.2, stage="MID")
    f = L.align_pair("s" * 64, "perez", (a, b),
                     C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert f.stage == "MID"
    assert f.stage in C.STAGES


def test_2025_classified_non_pristine():
    blob = open(
        ROOT / "results" / "v3" / "v3_8b" / "alignment_contract.json"
    ).read()
    assert "NON_PRISTINE" in blob
    assert "pristine" not in blob.lower().replace("non_pristine", "")


def test_temporal_poison_inaccessible():
    import raceintel.consensus.adapters as mod
    import raceintel.consensus.alignment as alg
    blob = (open(mod.__file__).read() + open(alg.__file__).read())
    blob = "\n".join(
        ln for ln in blob.splitlines()
        if "from __future__" not in ln).lower()
    for token in ("is_winner", "position_final", "y_true",
                  "future_", "winner label"):
        assert token not in blob, token


def test_reproducibility_exact():
    a = _rec(C.SourceId.V3_1B_LOGISTIC, C.Target.WIN, 0.31)
    b = _rec(C.SourceId.MC2_E, C.Target.WIN, 0.22)
    f1 = L.align_pair("s" * 64, "perez", (a, b),
                      C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    f2 = L.align_pair("s" * 64, "perez", (a, b),
                      C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert f1 == f2
    m1 = L.align_multi("s" * 64, "perez", (a, b),
                       (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E))
    m2 = L.align_multi("s" * 64, "perez", (a, b),
                       (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E))
    assert m1 == m2
