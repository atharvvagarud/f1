"""F2 tests: registry, validation, label guard, contracts, engine.

Offline, synthetic-only (plus frozen-schema cross-checks for the
passthrough inventory). No network, no Parquet reads, no pandas.
"""

import json

import pytest

from raceintel import contracts as C
from raceintel.pipeline import d9schema as D9
from raceintel.features import (
    FeatureDef,
    FeatureFamily,
    FeatureRegistry,
    FeatureRequest,
    FeatureResult,
    FeatureStatus,
    InvalidFeatureError,
    MinHistory,
    MinHistoryKind,
    MissingPolicy,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f2_registry,
    features_for_batch,
    features_for_state,
    label_outcome_fields,
    results_equal,
    validate_definition,
)
from raceintel.features.engine import PARITY_ABS_TOL, PARITY_REL_TOL


def _base(**kw):
    args = {
        "name": "pace_mean_3",
        "family": FeatureFamily.PACE,
        "version": 1,
        "dtype": "float64",
        "unit": "seconds",
        "description": "trailing eligible mean",
        "sources": ("driver_lap_state_d9.lap_time_s",),
        "formula_ref": "F5 contract",
        "temporal_rule": TemporalRule.DRIVER_PREFIX,
        "sync": SyncRequirement.NONE,
        "min_history": MinHistory(MinHistoryKind.COUNT, n=3),
        "missing": MissingPolicy.NULL_IF_INSUFFICIENT_HISTORY,
        "availability": C.Availability.LAP_END,
        "predictive_eligible": True,
        "status": FeatureStatus.CANDIDATE,
    }
    args.update(kw)
    return FeatureDef(**args)


# --- registry basics ---

def test_valid_definition_accepted():
    r = FeatureRegistry()
    r.register(_base())
    assert len(r) == 1
    assert r.get("pace_mean_3").version == 1


def test_duplicate_name_rejected():
    r = FeatureRegistry()
    r.register(_base())
    with pytest.raises(InvalidFeatureError):
        r.register(_base())


def test_deterministic_ordering():
    r = FeatureRegistry()
    r.register(_base(name="zeta"))
    r.register(_base(name="alpha"))
    assert r.names() == ["alpha", "zeta"]
    assert [f.name for f in r] == ["alpha", "zeta"]


def test_deterministic_serialization_and_fingerprint():
    r1, r2 = FeatureRegistry(), FeatureRegistry()
    r1.register(_base(name="b_feat"))
    r1.register(_base(name="a_feat"))
    r2.register(_base(name="a_feat"))
    r2.register(_base(name="b_feat"))
    assert r1.to_json() == r2.to_json()
    assert r1.fingerprint() == r2.fingerprint()
    assert len(r1.fingerprint()) == 64
    parsed = json.loads(r1.to_json())
    assert parsed["features"][0]["name"] == "a_feat"


# --- validation ---

def test_invalid_lineage_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(sources=()))
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(sources=("FastF1",)))
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(sources=("no-dot",)))


def test_invalid_temporal_rule_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(temporal_rule="same_lap"))


def test_invalid_units_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(unit=""))
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(unit="  "))
    ok = _base(unit="unitless")
    validate_definition(ok)


def test_invalid_dtype_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(dtype="float32"))


def test_invalid_min_history_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(min_history=MinHistory(MinHistoryKind.COUNT, n=0)))
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(min_history=MinHistory(MinHistoryKind.POLICY_REF,
                                         policy_ref="")))
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(min_history=MinHistory(MinHistoryKind.NONE, n=3)))


def test_contradictory_predictive_status_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(status=FeatureStatus.DEFERRED, predictive_eligible=True))
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(status=FeatureStatus.PASSTHROUGH,
                  predictive_eligible=False))
    with pytest.raises(InvalidFeatureError):
        validate_definition(_base(missing="not-a-policy"))


def test_fallback_requires_justification():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(missing=MissingPolicy.DETERMINISTIC_FALLBACK,
                  fallback_description=""))
    validate_definition(
        _base(missing=MissingPolicy.DETERMINISTIC_FALLBACK,
              fallback_description="fallback := 0 justified because ..."))


# --- temporal safety metadata ---

def test_predictive_post_race_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(availability=C.Availability.POST_RACE))


def test_predictive_label_only_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(availability=C.Availability.LABEL_ONLY))


def test_cross_driver_without_sync_rejected():
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(name="gap_to_leader", family=FeatureFamily.GAP,
                  sync=SyncRequirement.NONE))
    ok = _base(name="gap_to_leader", family=FeatureFamily.GAP,
               sync=SyncRequirement.SYNCHRONIZED_FIELD,
               temporal_rule=TemporalRule.SYNCHRONIZED_FIELD)
    validate_definition(ok)


def test_same_lap_semantics_inexpressible():
    members = {m.value for m in SyncRequirement} | \
              {m.value for m in TemporalRule}
    assert "same_lap" not in members
    assert not any("same" in v and "lap" in v for v in members)


# --- label guard ---

def test_label_fields_known_from_phase1_metadata():
    outcomes = label_outcome_fields()
    for col in ("winner_flag", "podium_flag", "points_finish_flag",
                "position_final", "classified_position", "points"):
        assert col in outcomes


def test_label_fields_rejected_as_predictive():
    for col in ("winner_flag", "position_final", "points"):
        with pytest.raises(InvalidFeatureError):
            validate_definition(_base(name=col))
        with pytest.raises(InvalidFeatureError):
            validate_definition(
                _base(name="sneaky", sources=(f"race_driver_labels.{col}",)))


def test_no_dnf_target_registrable():
    # hist_results.dnf_flag is LABEL_ONLY in Phase-1 contracts, so any
    # predictive feature sourcing it is rejected by the label guard.
    with pytest.raises(InvalidFeatureError):
        validate_definition(
            _base(name="driver_dnf_rate_5",
                  sources=("hist_results.dnf_flag",)))


def test_normal_d9_predictive_field_accepted():
    validate_definition(_base(name="lap_time_s",
                              sources=("driver_lap_state_d9.lap_time_s",)))


# --- passthrough inventory ---

def test_f2_registry_counts():
    r = build_f2_registry()
    assert len(r) == 24  # 23 passthroughs + planned grid
    statuses = {f.name: f.status for f in r}
    assert statuses["grid_position"] is FeatureStatus.PLANNED
    assert all(s is FeatureStatus.PASSTHROUGH
               for n, s in statuses.items() if n != "grid_position")


def test_passthrough_matches_phase1_schema():
    from raceintel.features.registry import _phase1_field
    r = build_f2_registry()
    for f in r:
        if f.status is not FeatureStatus.PASSTHROUGH:
            continue
        src = _phase1_field(f.name)
        assert f.dtype == src.dtype
        assert f.unit == src.unit
        assert f.availability is src.availability
        assert f.predictive_eligible and src.predictive_eligible
        assert f.sources == (f"driver_lap_state_d9.{f.name}",)


def test_no_non_predictive_field_promoted():
    from raceintel.features.registry import _phase1_field
    import raceintel.pipeline.d6schema as D6
    import raceintel.pipeline.d7schema as D7
    non_pred = {f.name for f in list(D6.STATE_FIELDS)
                + list(D7.EXTENSION_FIELDS) + list(D9.STATE_EXTENSION_FIELDS)
                if not f.predictive_eligible}
    assert non_pred  # guard is non-vacuous
    registered = set(build_f2_registry().names())
    assert not (non_pred & registered)


def test_passthrough_expected_names():
    r = build_f2_registry()
    for name in ("position", "race_progress_frac", "track_state",
                 "flag_safety_car", "pit_stops_completed_so_far",
                 "laps_since_last_pit_stop", "stint_lap", "compound",
                 "wx_air_temp_c", "stint_compound"):
        assert name in r.names()


# --- versioning ---

def test_version_policy():
    r = build_f2_registry()
    fp1 = r.fingerprint()
    # v1 (F2) -> v2 (F5) -> v3 (F6) -> v4 (F7) -> v5 (F8) -> v6 (F9)
    # -> v7 (F10) -> v8 (F11, +3).
    assert r.to_dict()["feature_set_version"] == "v8"
    # metadata-identical rebuild is stable
    assert build_f2_registry().fingerprint() == fp1


# --- request/result contracts ---

def test_request_identity_deterministic():
    q1 = FeatureRequest("2023-r01-R", "max_verstappen", 28, 6522.749)
    q2 = FeatureRequest("2023-r01-R", "max_verstappen", 28, 6522.749)
    assert q1.key() == q2.key()
    assert "winner" not in q1.key() and "points" not in q1.key()


def test_result_equality_null_semantics():
    base = {"race_id": "r", "driver_id": "d", "lap_number": 1,
            "state_time_s": 10.0, "feature_set_version": "v1"}
    a = FeatureResult(values=(("x", None),), **base)
    b = FeatureResult(values=(("x", None),), **base)
    c = FeatureResult(values=(("x", 1.0),), **base)
    assert results_equal(a, b)
    assert not results_equal(a, c)


def test_result_equality_float_tolerance_and_order():
    base = {"race_id": "r", "driver_id": "d", "lap_number": 1,
            "state_time_s": 10.0, "feature_set_version": "v1"}
    a = FeatureResult(values=(("x", 0.1 + 0.2), ("y", "SOFT")), **base)
    b = FeatureResult(values=(("x", 0.3), ("y", "SOFT")), **base)
    assert results_equal(a, b)
    d = FeatureResult(values=(("y", "SOFT"), ("x", 0.3)), **base)
    assert not results_equal(a, d)  # ordering matters
    e = FeatureResult(feature_set_version="v2",
                      values=(("x", 0.3), ("y", "SOFT")),
                      race_id="r", driver_id="d", lap_number=1,
                      state_time_s=10.0)
    assert not results_equal(a, e)
    f = FeatureResult(values=(("x", 0.3), ("y", "MEDIUM")), **base)
    assert not results_equal(a, f)


def test_parity_tolerances_sane():
    assert 0 < PARITY_REL_TOL <= 1e-6
    assert 0 < PARITY_ABS_TOL <= 1e-9


# --- engine skeleton ---

def test_unfinished_calculator_fails_explicitly():
    q = FeatureRequest("2023-r01-R", "max_verstappen", 28, 6522.749)
    r = build_f2_registry()
    with pytest.raises(NoCalculatorError):
        features_for_state(q, r)
    with pytest.raises(NoCalculatorError):
        features_for_batch([q], r)


def test_no_dummy_values_possible():
    assert issubclass(NoCalculatorError, NotImplementedError)
