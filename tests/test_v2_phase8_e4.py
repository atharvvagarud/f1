"""Phase-8 E4: local checkpoint explainability of the frozen winner model.

Pins: the additive local contract; frozen identity; exact Phase-2 matrix
lookup (no tolerance/nearest/fall-forward); the 84 -> 106 transform; the
exact 106-dimension contribution vector; logit/sigmoid reconstruction to
machine precision; three-way consistency (explanation / frozen estimator /
E2 cached replay probability); exact 106 -> 84 canonical grouping;
missingness + categorical semantics; deterministic top-N + omitted
accounting; the 2025 and label firewalls; post-T mutation invariance; the
API endpoint semantics; and the local language contract.

Local artifacts are built once per session with the frozen matrix backend
into a tmp checkpoint dir (never the gitignored production cache). No 2025
row, label or target is ever read.
"""

from __future__ import annotations

import copy
import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.v2_explanation_service import (  # noqa: E402
    DriverNotObservableError,
    ExplanationFeatureUnavailableError,
    UnknownDriverError,
    V2ExplanationService,
    get_v2_explanation_service,
)
from api.v2_replay_service import (  # noqa: E402
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    V2ReplayService,
)
from scripts.build_replay_prediction_cache import (  # noqa: E402
    SeasonStatesCache,
    build_one_race,
    load_race_inputs,
    race_season,
)
from scripts.replay_feature_matrix import (  # noqa: E402
    IDENTITY_COLUMNS,
    FrozenReplayFeatureMatrix,
    MatrixIdentityError,
    MatrixScopeError,
)
from v2 import explainability as E3  # noqa: E402
from v2 import local_explainability as E4  # noqa: E402
from v2.config import V2Paths  # noqa: E402
from v2.features.build_matrix import load_history  # noqa: E402
from v2.local_explainability import (  # noqa: E402
    CachedPredictionMismatchError,
    LocalExplanationError,
    LocalExplanationIdentity,
    LocalReconstructionError,
)
from v2.model_lab import serving as SERVING  # noqa: E402
from v2.prediction import ModelIdentity  # noqa: E402
from v2.race_state_reconstruction import (  # noqa: E402
    RaceNotFoundError,
    RaceStateReconstructor,
)

RACE_FULL = "2023-r12-R"   # early + mid + late checkpoints
RACE_SMALL = "2021-r12-R"  # 3 checkpoints, thin/partial history
RACES = ((2023, RACE_FULL), (2021, RACE_SMALL))

SPEC_FINGERPRINT = (
    "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d")
SERVING_SHA = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4")

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")


# ---------------------------------------------------------------------------
# Session fixtures: build small real checkpoint artifacts with the frozen
# matrix backend (never the production cache).
# ---------------------------------------------------------------------------

def _phase2_content_hash() -> str:
    with open(ROOT / "docs" / "PHASE4_FREEZE_MANIFEST.json") as handle:
        return json.load(handle)["phase2"]["content_hash"]


def _build_corpus():
    state_parts, result_parts = [], []
    for season, race in RACES:
        frame = pd.read_parquet(ROOT / D9.format(season=season))
        state_parts.append(frame[frame["race_id"] == race].copy())
        result_parts.append(pd.read_parquet(
            ROOT / RESULTS.format(season=season, race=race)))
    states = pd.concat(state_parts, ignore_index=True)
    results = pd.concat(result_parts, ignore_index=True)
    return states, results, RaceStateReconstructor(states, results)


@pytest.fixture(scope="session")
def stack(tmp_path_factory):
    predictor = E3.load_frozen_explanation_model()
    history = load_history(V2Paths.resolve())
    matrix = FrozenReplayFeatureMatrix.load(str(ROOT))
    map_entries = E3.build_transformed_feature_map(predictor)
    sci = {
        "feature_set": SERVING.EXPECTED_FEATURE_SET,
        "feature_set_version": "v8",
        "serving_artifact_sha256": E3.artifact_sha256(
            SERVING.default_serving_artifact_path()),
        "model_specification_fingerprint": predictor.specification_fingerprint,
        "phase2_content_hash": _phase2_content_hash(),
        "probability_semantics": "INDEPENDENT_BINARY",
    }
    checkpoints_dir = str(tmp_path_factory.mktemp("e4_checkpoints"))
    season_cache = SeasonStatesCache(str(ROOT / "data" / "v2" / "processed"))
    for race_id in (RACE_FULL, RACE_SMALL):
        season = race_season(race_id)
        build_one_race(
            race_id, checkpoints_dir=checkpoints_dir, predictor=predictor,
            history=history, phase2_hash=sci["phase2_content_hash"],
            force=True, max_checkpoints=None, season_cache=season_cache,
            feature_source="matrix", matrix=matrix)
    states, results, recon = _build_corpus()
    return SimpleNamespace(
        predictor=predictor, history=history, matrix=matrix,
        map_entries=map_entries, scientific=sci,
        checkpoints_dir=checkpoints_dir, states=states, results=results,
        recon=recon)


@pytest.fixture(scope="session")
def replay_service(stack):
    return V2ReplayService(
        stack.states, stack.recon, [r for _, r in RACES],
        checkpoints_dir=stack.checkpoints_dir,
        scientific_inputs=dict(stack.scientific))


@pytest.fixture(scope="session")
def service(stack, replay_service):
    return V2ExplanationService(
        replay_service, stack.predictor, stack.matrix,
        map_entries=stack.map_entries)


def _checkpoints(replay_service, race_id):
    return replay_service.get_series(race_id).checkpoints


def _entry(snapshot, driver_id):
    return next(e for e in snapshot["predictions"]
                if e["driver_id"] == driver_id)


def _observable_driver(replay_service, race_id, checkpoint_index):
    checkpoint = _checkpoints(replay_service, race_id)[checkpoint_index]
    snap = replay_service.get_prediction(
        race_id, checkpoint.frame_index)["prediction"]
    return next(e["driver_id"] for e in snap["predictions"]
                if e["observable"]), checkpoint, snap


def _explain(service, replay_service, race_id, checkpoint_index):
    driver_id, checkpoint, _ = _observable_driver(
        replay_service, race_id, checkpoint_index)
    return service.get_explanation(
        race_id, checkpoint.frame_index, driver_id)


# ---------------------------------------------------------------------------
# PART A — contract + frozen identity
# ---------------------------------------------------------------------------

def test_contract_version_and_semantics():
    assert E4.LOCAL_EXPLANATION_CONTRACT_VERSION == "v1"
    assert E4.LOCAL_EXPLANATION_FORMAT == "local-explanation-v1"
    assert E4.EXPLANATION_SPACE == "LOG_ODDS"
    assert E4.PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"
    assert E4.LOGIT_ABS_TOL <= 1e-12
    assert E4.PROBABILITY_ABS_TOL <= 1e-12


def test_contract_is_additive_replay_untouched():
    from v2.replay_predictions import (
        ARTIFACT_FORMAT,
        REPLAY_PREDICTION_CONTRACT_VERSION,
    )
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert ARTIFACT_FORMAT == "replay-checkpoints-v1"
    assert E4.LOCAL_EXPLANATION_FORMAT != ARTIFACT_FORMAT
    source = (ROOT / "v2" / "local_explainability.py").read_text()
    assert "replay_predictions" not in source  # never mutates replay contract


def test_model_identity(service, stack):
    payload = _explain(service, service._replay, RACE_FULL, 0)
    model = payload["model_identity"]
    assert model["feature_set"] == "ALL_84"
    assert model["feature_set_version"] == "v8"
    assert model["estimator_class"] == "LogisticRegression"
    assert model["transformed_dim"] == 106
    assert model["canonical_feature_count"] == 84
    assert model["specification_fingerprint"] == SPEC_FINGERPRINT
    assert model["calibration_method"] == "RAW"
    assert model["probability_semantics"] == "INDEPENDENT_BINARY"


def test_feature_identity_exact(service, stack):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 0)
    payload = service.get_explanation(
        RACE_FULL, checkpoint.frame_index, driver_id)
    fid = payload["identity"]["feature_identity"]
    entry = _entry(snap, driver_id)
    assert fid == {
        "race_id": RACE_FULL,
        "driver_id": driver_id,
        "lap_number": entry["observed_lap_number"],
        "state_time_s": entry["observed_time_s"],
    }
    assert payload["identity"]["frame_index"] == checkpoint.frame_index


# ---------------------------------------------------------------------------
# PART B/C/D — exact matrix lookup, transform, contributions, reconstruction
# ---------------------------------------------------------------------------

def test_exact_matrix_lookup_matches_frozen_row(service, stack):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 3)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        RACE_FULL, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    race_frame = stack.matrix.race_slice(RACE_FULL)
    direct = race_frame[
        (race_frame["driver_id"] == driver_id)
        & (race_frame["lap_number"] == int(entry["observed_lap_number"]))
        & (race_frame["state_time_s"] == float(entry["observed_time_s"]))][
            list(stack.predictor.feature_names)]
    assert len(direct) == 1
    pd.testing.assert_frame_equal(
        row.reset_index(drop=True), direct.reset_index(drop=True),
        check_dtype=False)


def test_transform_is_84_to_106(service, stack):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 3)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        RACE_FULL, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    transformed = stack.predictor._preprocessor.transform(row)
    assert transformed.shape == (1, 106)
    assert np.all(np.isfinite(transformed))


def test_logit_and_probability_exact(service, stack):
    payload = _explain(service, service._replay, RACE_FULL, 2)
    rec = payload["reconstruction"]
    assert abs(rec["residual"]) <= E4.LOGIT_ABS_TOL
    assert payload["logit"] == pytest.approx(
        rec["estimator_decision_function"], abs=E4.LOGIT_ABS_TOL)
    assert payload["probability"] == pytest.approx(
        payload["model_probability"], abs=E4.PROBABILITY_ABS_TOL)


def test_cached_probability_three_way(service, replay_service):
    for index in range(3):
        payload = _explain(service, replay_service, RACE_FULL, index)
        assert payload["cached_probability"] is not None
        assert payload["probability"] == pytest.approx(
            payload["cached_probability"], abs=E4.PROBABILITY_ABS_TOL)
        assert payload["cache_status"] == "HIT"


def test_contribution_vector_matches_logit(service, replay_service):
    driver_id, checkpoint, _ = _observable_driver(
        replay_service, RACE_FULL, 1)
    payload = service.get_explanation(
        RACE_FULL, checkpoint.frame_index, driver_id)
    rec = payload["reconstruction"]
    assert rec["transformed_contribution_sum"] == pytest.approx(
        payload["logit"] - payload["intercept"], abs=E4.LOGIT_ABS_TOL)
    assert rec["canonical_contribution_sum"] == pytest.approx(
        rec["transformed_contribution_sum"], abs=E4.LOGIT_ABS_TOL)


# ---------------------------------------------------------------------------
# PART E/G/H — grouping, missingness, top-N, accounting
# ---------------------------------------------------------------------------

def _domain(service, replay_service, race_id, index):
    """Full domain payload (with all 84 canonical rows) for assertions."""
    driver_id, checkpoint, snap = _observable_driver(
        replay_service, race_id, index)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        race_id, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    identity = LocalExplanationIdentity(
        race_id=race_id, frame_index=checkpoint.frame_index,
        driver_id=driver_id,
        observed_lap_number=int(entry["observed_lap_number"]),
        observed_time_s=float(entry["observed_time_s"]),
        state_time_s=float(snap["state_time_s"]),
        anchor_driver_id=str(snap["anchor_driver_id"]),
        anchor_lap_number=int(snap["anchor_lap_number"]),
        anchor_state_time_s=float(snap["state_time_s"]),
        checkpoint_reasons=tuple(checkpoint.reasons),
        leader_lap=checkpoint.leader_lap,
        observed_position=entry["observed_position"],
        observation_age_s=entry["observation_age_s"])
    return E4.explain_winner_prediction(
        service._predictor, row, identity,
        cached_probability=float(entry["winner_probability"]),
        map_entries=service._map_entries)


def test_canonical_grouping_covers_84_exactly(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 2)
    rows = payload["canonical_contributions"]
    assert len(rows) == 84
    assert [r["canonical_feature"] for r in rows] == \
        list(service._predictor.feature_names)
    assert len({r["canonical_feature"] for r in rows}) == 84
    total_dims = sum(len(r["transformed_dimensions"]) for r in rows)
    assert total_dims == 106


def test_canonical_grouping_sums_transformed_exactly(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 4)
    grouped = sum(r["log_odds_contribution"]
                  for r in payload["canonical_contributions"])
    assert grouped == pytest.approx(
        payload["reconstruction"]["transformed_contribution_sum"],
        abs=E4.LOGIT_ABS_TOL)


def test_categorical_block_grouped_exactly(service, replay_service, stack):
    payload = _domain(service, replay_service, RACE_FULL, 3)
    categorical = [r for r in payload["canonical_contributions"]
                   if r["feature_type"] == "categorical"]
    assert {r["canonical_feature"] for r in categorical} == {
        "compound", "stint_compound", "track_state"}
    for row in categorical:
        manual = sum(d["log_odds_contribution"]
                     for d in row["transformed_dimensions"])
        assert row["log_odds_contribution"] == pytest.approx(
            manual, abs=E4.LOGIT_ABS_TOL)
        assert row["imputed_value"] is not None or \
            row["active_category"] is not None or \
            row["input_state"] in (E4.MISSING_CATEGORY, E4.UNKNOWN_CATEGORY)


def test_numeric_and_boolean_single_dimension(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 1)
    for row in payload["canonical_contributions"]:
        if row["feature_type"] in ("numeric", "boolean"):
            assert len(row["transformed_dimensions"]) == 1


def test_direction_labels_follow_sign(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 2)
    for row in payload["canonical_contributions"]:
        contribution = row["log_odds_contribution"]
        if contribution > 0:
            assert row["direction"] == E4.DIRECTION_INCREASES
        elif contribution < 0:
            assert row["direction"] == E4.DIRECTION_DECREASES
        else:
            assert row["direction"] == E4.DIRECTION_NEUTRAL
    joined = json.dumps(payload).lower()
    for bad in ("helps driver", "hurts driver", "positive race factor",
                "negative race factor"):
        assert bad not in joined


def _synthetic_row(service, replay_service, race_id, index, mutate):
    driver_id, checkpoint, snap = _observable_driver(
        replay_service, race_id, index)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        race_id, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    mutate(row)
    return row, entry, checkpoint, snap


def _identity_from(checkpoint, snap, driver_id, entry):
    return LocalExplanationIdentity(
        race_id=snap["race_id"], frame_index=checkpoint.frame_index,
        driver_id=driver_id,
        observed_lap_number=int(entry["observed_lap_number"]),
        observed_time_s=float(entry["observed_time_s"]),
        state_time_s=float(snap["state_time_s"]),
        anchor_driver_id=str(snap["anchor_driver_id"]),
        anchor_lap_number=int(snap["anchor_lap_number"]),
        anchor_state_time_s=float(snap["state_time_s"]),
        checkpoint_reasons=tuple(checkpoint.reasons),
        leader_lap=checkpoint.leader_lap)


def test_numeric_imputation_state(service, replay_service):
    def mutate(row):
        row.iloc[0, row.columns.get_loc("position")] = np.nan
    row, entry, checkpoint, snap = _synthetic_row(
        service, replay_service, RACE_FULL, 1, mutate)
    payload = E4.explain_winner_prediction(
        service._predictor, row,
        _identity_from(checkpoint, snap, entry["driver_id"], entry),
        map_entries=service._map_entries)
    node = next(r for r in payload["canonical_contributions"]
                if r["canonical_feature"] == "position")
    assert node["input_state"] == E4.IMPUTED_NUMERIC_MEDIAN
    assert node["raw_value"] is None
    median = service._predictor._preprocessor.transformer.named_transformers_[
        "num"].named_steps["impute"].statistics_[
            list(service._predictor._preprocessor.numeric_columns).index(
                "position")]
    assert node["imputed_value"] == pytest.approx(float(median))


def test_boolean_imputation_state(service, replay_service):
    boolean = list(service._predictor._preprocessor.boolean_columns)

    def mutate(row):
        row.iloc[0, row.columns.get_loc(boolean[0])] = np.nan
    row, entry, checkpoint, snap = _synthetic_row(
        service, replay_service, RACE_FULL, 1, mutate)
    payload = E4.explain_winner_prediction(
        service._predictor, row,
        _identity_from(checkpoint, snap, entry["driver_id"], entry),
        map_entries=service._map_entries)
    node = next(r for r in payload["canonical_contributions"]
                if r["canonical_feature"] == boolean[0])
    assert node["input_state"] == E4.IMPUTED_BOOLEAN_MODE
    assert node["raw_value"] is None


def test_missing_categorical_state(service, replay_service):
    def mutate(row):
        row.iloc[0, row.columns.get_loc("compound")] = np.nan
    row, entry, checkpoint, snap = _synthetic_row(
        service, replay_service, RACE_FULL, 1, mutate)
    payload = E4.explain_winner_prediction(
        service._predictor, row,
        _identity_from(checkpoint, snap, entry["driver_id"], entry),
        map_entries=service._map_entries)
    node = next(r for r in payload["canonical_contributions"]
                if r["canonical_feature"] == "compound")
    assert node["input_state"] == E4.MISSING_CATEGORY
    assert node["imputed_value"] == "MISSING"
    assert node["active_category"] == "MISSING"


def test_unknown_categorical_state_is_all_zero(service, replay_service):
    def mutate(row):
        row.iloc[0, row.columns.get_loc("compound")] = "SUPER_HYPER_SOFT"
    row, entry, checkpoint, snap = _synthetic_row(
        service, replay_service, RACE_FULL, 1, mutate)
    payload = E4.explain_winner_prediction(
        service._predictor, row,
        _identity_from(checkpoint, snap, entry["driver_id"], entry),
        map_entries=service._map_entries)
    node = next(r for r in payload["canonical_contributions"]
                if r["canonical_feature"] == "compound")
    assert node["input_state"] == E4.UNKNOWN_CATEGORY
    assert node["raw_value"] == "SUPER_HYPER_SOFT"
    assert node["active_category"] is None
    assert all(d["transformed_value"] == 0.0
               for d in node["transformed_dimensions"])
    assert node["log_odds_contribution"] == 0.0


def test_top_positive_and_negative_ordering(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 2)
    positive = payload["top_positive"]
    negative = payload["top_negative"]
    assert len(positive) <= E4.TOP_N
    assert len(negative) <= E4.TOP_N
    assert all(r["log_odds_contribution"] > 0 for r in positive)
    assert all(r["log_odds_contribution"] < 0 for r in negative)
    assert positive == sorted(
        positive, key=lambda r: (-r["log_odds_contribution"],
                                 r["canonical_feature"]))
    assert negative == sorted(
        negative, key=lambda r: (r["log_odds_contribution"],
                                 r["canonical_feature"]))


def test_top_tie_break_is_canonical_name(service, replay_service):
    rows = [
        {"canonical_feature": "b", "log_odds_contribution": 0.5},
        {"canonical_feature": "a", "log_odds_contribution": 0.5},
        {"canonical_feature": "c", "log_odds_contribution": 0.5},
    ]
    top, _ = E4._top_entries(rows, True, 2)
    assert [r["canonical_feature"] for r in top] == ["a", "b"]


def test_omitted_contribution_accounting(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 3)
    acc = payload["accounting"]
    assert acc["shown_positive_log_odds"] + \
        acc["omitted_positive_log_odds"] == pytest.approx(
            acc["total_positive_log_odds"], abs=E4.LOGIT_ABS_TOL)
    assert acc["shown_negative_log_odds"] + \
        acc["omitted_negative_log_odds"] == pytest.approx(
            acc["total_negative_log_odds"], abs=E4.LOGIT_ABS_TOL)
    assert acc["omitted_positive_log_odds"] >= 0
    assert acc["omitted_negative_log_odds"] <= 0
    assert acc["top_n_reconstructs_prediction"] is False
    assert acc["full_decomposition_reconstructs_prediction"] is True


def test_public_projection_is_compact(service, replay_service):
    driver_id, checkpoint, _ = _observable_driver(
        replay_service, RACE_FULL, 1)
    public = service.get_explanation(
        RACE_FULL, checkpoint.frame_index, driver_id)
    assert "canonical_contributions" not in public
    assert "transformed_features" not in public
    assert len(public["top_positive"]) <= E4.TOP_N
    assert len(public["top_negative"]) <= E4.TOP_N
    for key in ("contract_version", "identity", "model_identity",
                "probability", "logit", "intercept", "accounting"):
        assert key in public


def test_no_probability_normalization(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 0)
    assert payload["probability_semantics"] == "INDEPENDENT_BINARY"
    joined = json.dumps(payload).lower()
    for bad in ("probabilities normalized", "probability share",
                "vote share", "softmax"):
        assert bad not in joined


def test_determinism(service, replay_service):
    first = _domain(service, replay_service, RACE_FULL, 1)
    second = _domain(service, replay_service, RACE_FULL, 1)
    assert E3.render_global_explanation(first) == \
        E3.render_global_explanation(second)


# ---------------------------------------------------------------------------
# Firewalls + red team
# ---------------------------------------------------------------------------

def test_2025_firewall_matrix_and_service(service, replay_service):
    with pytest.raises(MatrixScopeError):
        service._matrix.race_slice("2025-r01-R")
    with pytest.raises(RaceNotFoundError):
        service.get_explanation("2025-r01-R", 0, "verstappen")


def test_label_firewall_matrix_columns(stack):
    forbidden = {"is_winner", "final_position", "classified_flag",
                 "eligible_is_winner", "eligible_is_podium",
                 "eligible_scored_points"}
    assert not (set(stack.matrix._frame.columns) & forbidden)
    assert set(stack.matrix._frame.columns) == (
        set(stack.matrix.feature_names) | set(IDENTITY_COLUMNS)
        | {"season"})


def test_classified_flag_and_labels_not_consumed(stack):
    source = (ROOT / "v2" / "local_explainability.py").read_text()
    for token in ("is_winner", "classified_flag", "eligible_is_winner",
                  "read_parquet", "final_position"):
        assert token not in source


def test_nearest_timestamp_fails_closed(service):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 0)
    entry = _entry(snap, driver_id)
    with pytest.raises(ExplanationFeatureUnavailableError):
        service._resolve_exact_row(
            RACE_FULL, driver_id, int(entry["observed_lap_number"]),
            float(entry["observed_time_s"]) + 0.001)


def test_missing_exact_row_fails_closed(stack):
    frame = stack.matrix._frame
    victim = frame[frame["race_id"] == RACE_FULL].iloc[0]
    pruned = frame.drop(victim.name).reset_index(drop=True)
    backend = FrozenReplayFeatureMatrix(
        pruned, stack.matrix.feature_names, stack.matrix.manifest_record)
    from scripts.replay_feature_matrix import MatrixLookupError
    want = pd.DataFrame(
        [[victim["race_id"], victim["driver_id"], int(victim["lap_number"]),
          float(victim["state_time_s"])]], columns=list(IDENTITY_COLUMNS))
    with pytest.raises(MatrixLookupError):
        backend.lookup(want, backend.race_slice(RACE_FULL))


def test_duplicate_matrix_identity_fails_closed(stack):
    frame = stack.matrix._frame
    dup = pd.concat([frame.iloc[:1], frame], ignore_index=True)
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix(dup, stack.matrix.feature_names,
                                  stack.matrix.manifest_record)


def test_feature_order_changed_fails_closed(service, replay_service):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 0)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        RACE_FULL, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    shuffled = row[list(row.columns[1:]) + [row.columns[0]]]
    with pytest.raises(LocalExplanationError):
        E4.explain_winner_prediction(
            service._predictor, shuffled,
            _identity_from(checkpoint, snap, driver_id, entry))


def test_coefficient_mismatch_fails_closed(service, replay_service):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 0)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        RACE_FULL, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    tampered = [dict(e) for e in service._map_entries]
    tampered[0] = {**tampered[0], "coefficient": tampered[0]["coefficient"] + 0.5}
    with pytest.raises(LocalExplanationError):
        E4.explain_winner_prediction(
            service._predictor, row,
            _identity_from(checkpoint, snap, driver_id, entry),
            map_entries=tampered)


def test_cached_probability_altered_fails_closed(service, replay_service):
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 0)
    entry = _entry(snap, driver_id)
    row = service._resolve_exact_row(
        RACE_FULL, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    with pytest.raises(CachedPredictionMismatchError):
        E4.explain_winner_prediction(
            service._predictor, row,
            _identity_from(checkpoint, snap, driver_id, entry),
            cached_probability=float(entry["winner_probability"]) + 0.1)


def test_top_n_accounting_cannot_be_dropped(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 2)
    assert "accounting" in payload
    assert payload["accounting"]["note"]


def test_language_contract(service, replay_service):
    payload = _domain(service, replay_service, RACE_FULL, 0)
    E3.assert_language_compliant(
        payload, forbidden=E4.LOCAL_FORBIDDEN_LANGUAGE)
    assert payload["language_contract"]["forbidden"]
    for text in ("this caused the win", "driver will win because",
                 "added 12% chance", "it helped the driver",
                 "the model thinks", "reason for the win"):
        with pytest.raises(E3.ExplainabilityError):
            E3.assert_language_compliant(
                {"note": text}, forbidden=E4.LOCAL_FORBIDDEN_LANGUAGE)


def test_no_shap_in_local_module():
    source = (ROOT / "v2" / "local_explainability.py").read_text()
    assert "import shap" not in source
    assert "shap." not in source


def test_post_t_mutation_invariance(service, replay_service, stack):
    """Post-T mutations cannot move the exact frozen row at T.

    Mirrors the Phase-2 bounded temporal-safety philosophy: the explanation
    consumes only the frozen Phase-2 row at the checkpoint identity T, so
    overwriting every later row with garbage leaves both the resolved row
    and the explanation byte-identical.
    """
    driver_id, checkpoint, snap = _observable_driver(
        service._replay, RACE_FULL, 1)
    entry = _entry(snap, driver_id)
    lap = int(entry["observed_lap_number"])
    time_s = float(entry["observed_time_s"])
    baseline = service.get_explanation(
        RACE_FULL, checkpoint.frame_index, driver_id)
    original_row = service._resolve_exact_row(
        RACE_FULL, driver_id, lap, time_s)

    mutated_frame = stack.matrix._frame.copy()
    future = mutated_frame["state_time_s"] > time_s + 1e-9
    assert future.any()
    for name in stack.matrix.feature_names:
        kind = mutated_frame[name].dtype.kind
        if kind == "b":
            mutated_frame.loc[future, name] = True
        elif kind in "iu":
            mutated_frame.loc[future, name] = 999999
        elif kind == "f":
            mutated_frame.loc[future, name] = 999999.0
        else:
            mutated_frame.loc[future, name] = "MUTATED"
    mutated_backend = FrozenReplayFeatureMatrix(
        mutated_frame, stack.matrix.feature_names, stack.matrix.manifest_record)
    # Resolve the same identity against the mutated backend directly.
    joined = mutated_backend.lookup(
        pd.DataFrame([[RACE_FULL, driver_id, lap, time_s]],
                     columns=list(IDENTITY_COLUMNS)),
        mutated_backend.race_slice(RACE_FULL))
    mutated_row = joined.iloc[[0]][list(service._predictor.feature_names)]
    pd.testing.assert_frame_equal(
        mutated_row.reset_index(drop=True),
        original_row.reset_index(drop=True), check_dtype=False)
    again = service.get_explanation(
        RACE_FULL, checkpoint.frame_index, driver_id)
    assert E3.render_global_explanation(again) == \
        E3.render_global_explanation(baseline)


# ---------------------------------------------------------------------------
# API endpoint semantics
# ---------------------------------------------------------------------------

def _client(service):
    from fastapi.testclient import TestClient
    from api.main import app
    app.dependency_overrides[get_v2_explanation_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def _route(race_id, frame_index, driver_id):
    return (f"/v2/replay/{race_id}/frames/{frame_index}"
            f"/predictions/{driver_id}/explanation")


def test_api_hit(service, replay_service):
    driver_id, checkpoint, _ = _observable_driver(
        replay_service, RACE_SMALL, 0)
    client = _client(service)
    try:
        resp = client.get(_route(RACE_SMALL, checkpoint.frame_index,
                                 driver_id))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["explanation_space"] == "LOG_ODDS"
    assert body["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["cache_status"] == "HIT"
    assert body["identity"]["driver_id"] == driver_id
    assert body["accounting"]["top_n_reconstructs_prediction"] is False
    E3.assert_language_compliant(
        json.loads(resp.text), forbidden=E4.LOCAL_FORBIDDEN_LANGUAGE)


def test_api_unknown_driver(service, replay_service):
    _, checkpoint, _ = _observable_driver(replay_service, RACE_SMALL, 0)
    client = _client(service)
    try:
        resp = client.get(_route(RACE_SMALL, checkpoint.frame_index,
                                 "not_a_real_driver"))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_driver"


def test_api_unobservable_driver(service, replay_service):
    frame0 = replay_service.get_prediction(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[0].frame_index)
    unobs = [e["driver_id"] for e in frame0["prediction"]["predictions"]
             if not e["observable"]]
    if not unobs:
        pytest.skip("frame 0 has no unobservable roster member")
    client = _client(service)
    try:
        resp = client.get(_route(
            RACE_FULL, frame0["frame"]["frame_index"], unobs[0]))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "driver_not_observable"
    assert body["reason"] == "NO_OBSERVATION_AT_SNAPSHOT"


def test_api_non_checkpoint(service, replay_service):
    series = replay_service.get_series(RACE_SMALL)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(0, 30) if i not in hits)
    client = _client(service)
    try:
        resp = client.get(_route(RACE_SMALL, plain, "hamilton"))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_prediction_checkpoint"


def test_api_cache_missing_503(stack, replay_service):
    from api.v2_explanation_service import build_v2_explanation_service
    import tempfile
    empty = V2ReplayService(
        stack.states, stack.recon, [r for _, r in RACES],
        checkpoints_dir=tempfile.mkdtemp(),
        scientific_inputs=dict(stack.scientific))
    service = build_v2_explanation_service(
        replay_service=empty, predictor=stack.predictor, matrix=stack.matrix,
        map_entries=stack.map_entries)
    checkpoint = empty.get_series(RACE_SMALL).checkpoints[0]
    snap = replay_service.get_prediction(
        RACE_SMALL, checkpoint.frame_index)["prediction"]
    driver_id = next(e["driver_id"] for e in snap["predictions"]
                     if e["observable"])
    client = _client(service)
    try:
        resp = client.get(_route(RACE_SMALL, checkpoint.frame_index,
                                 driver_id))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_missing"


def test_api_unknown_race_and_2025(service):
    client = _client(service)
    try:
        assert client.get(_route("nope", 0, "hamilton")).status_code == 404
        resp = client.get(_route("2025-r01-R", 0, "hamilton"))
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_api_route_inventory_additive(service):
    client = _client(service)
    try:
        paths = client.get("/openapi.json").json()["paths"]
    finally:
        from api.main import app
        app.dependency_overrides.pop(get_v2_explanation_service, None)
    assert ("/v2/replay/{race_id}/frames/{frame_index}/predictions/"
            "{driver_id}/explanation") in paths
    for path in ("/v2/races/{race_id}/replay/timeline",
                 "/v2/races/{race_id}/replay/predictions/{frame_index}",
                 "/v2/races/{race_id}/states"):
        assert path in paths


# ---------------------------------------------------------------------------
# Performance (on-demand; characterizes whether a cache is needed)
# ---------------------------------------------------------------------------

def test_explanation_latency_characterized(service, replay_service, capsys):
    series = replay_service.get_series(RACE_FULL)
    # Full checkpoint field at one checkpoint + a warm single-driver repeat.
    checkpoints = [series.checkpoints[0],
                   series.checkpoints[len(series.checkpoints) // 2],
                   series.checkpoints[-1]]
    latencies = []
    for checkpoint in checkpoints:
        snap = replay_service.get_prediction(
            RACE_FULL, checkpoint.frame_index)["prediction"]
        for entry in snap["predictions"]:
            if not entry["observable"]:
                continue
            started = time.perf_counter()
            service.get_explanation(
                RACE_FULL, checkpoint.frame_index, entry["driver_id"])
            latencies.append((time.perf_counter() - started) * 1000)
    mid = series.checkpoints[len(series.checkpoints) // 2]
    snap = replay_service.get_prediction(
        RACE_FULL, mid.frame_index)["prediction"]
    driver_id = next(e["driver_id"] for e in snap["predictions"]
                     if e["observable"])
    single = []
    for _ in range(10):
        started = time.perf_counter()
        service.get_explanation(RACE_FULL, mid.frame_index, driver_id)
        single.append((time.perf_counter() - started) * 1000)
    latencies.sort()
    single.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
    with capsys.disabled():
        print(f"\n[E4-perf] field n={len(latencies)} p50={p50:.1f}ms "
              f"p95={p95:.1f}ms max={latencies[-1]:.1f}ms | "
              f"warm single p50={statistics.median(single):.1f}ms "
              f"p95={single[int(len(single) * 0.95)]:.1f}ms")
    assert p95 < 250.0  # comfortably interactive even on a slow runner
