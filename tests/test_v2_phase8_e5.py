"""Phase-8 E5: prediction-change (timeline) explainability.

Pins: the additive timeline-change contract; explicit previous-checkpoint
selection; first-checkpoint / driver-observability product states; exact
from/to checkpoint identity; three-way consistency (from/to cached
probabilities, from/to logits, canonical contribution deltas); the exact
delta reconstruction ``sum(dc_j) == z_B - z_A``; categorical / missingness /
imputation transitions; deterministic top-N delta ordering + omitted-delta
accounting; the zero-delta and cancellation cases; the 2025 and label
firewalls; temporal mutation invariance for A, B and the delta; the API
status semantics; and the change language contract.

Local artifacts are built once per session with the frozen matrix backend
into a tmp checkpoint dir (never the gitignored production cache). No 2025
row, label or target is ever read.
"""

from __future__ import annotations

import copy
import json
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
    UnknownDriverError,
    V2ExplanationService,
    get_v2_explanation_service,
)
from api.v2_replay_service import (  # noqa: E402
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    V2ReplayService,
)
from api.v2_timeline_explanation_service import (  # noqa: E402
    V2TimelineExplanationService,
    get_v2_timeline_explanation_service,
)
from scripts.build_replay_prediction_cache import (  # noqa: E402
    SeasonStatesCache,
    build_one_race,
    race_season,
)
from scripts.replay_feature_matrix import (  # noqa: E402
    IDENTITY_COLUMNS,
    FrozenReplayFeatureMatrix,
)
from v2 import explainability as E3  # noqa: E402
from v2 import local_explainability as E4  # noqa: E402
from v2 import timeline_explainability as E5  # noqa: E402
from v2.config import V2Paths  # noqa: E402
from v2.features.build_matrix import load_history  # noqa: E402
from v2.local_explainability import (  # noqa: E402
    LocalExplanationIdentity,
)
from v2.model_lab import serving as SERVING  # noqa: E402
from v2.race_state_reconstruction import (  # noqa: E402
    RaceNotFoundError,
    RaceStateReconstructor,
)

RACE_FULL = "2023-r12-R"   # early + mid + late checkpoints
RACE_SMALL = "2021-r12-R"  # 3 checkpoints, thin/partial history
RACES = ((2023, RACE_FULL), (2021, RACE_SMALL))

SPEC_FINGERPRINT = (
    "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d")

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")


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
    checkpoints_dir = str(tmp_path_factory.mktemp("e5_checkpoints"))
    season_cache = SeasonStatesCache(str(ROOT / "data" / "v2" / "processed"))
    for race_id in (RACE_FULL, RACE_SMALL):
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
def explanation_service(stack, replay_service):
    return V2ExplanationService(
        replay_service, stack.predictor, stack.matrix,
        map_entries=stack.map_entries)


@pytest.fixture(scope="session")
def change_service(replay_service, explanation_service):
    return V2TimelineExplanationService(replay_service, explanation_service)


def _checkpoints(replay_service, race_id):
    return replay_service.get_series(race_id).checkpoints


def _snapshot(replay_service, race_id, frame_index):
    return replay_service.get_prediction(race_id, frame_index)["prediction"]


def _entry(snapshot, driver_id):
    return next(e for e in snapshot["predictions"]
                if e["driver_id"] == driver_id)


def _observable_driver(replay_service, race_id, index):
    checkpoint = _checkpoints(replay_service, race_id)[index]
    snap = _snapshot(replay_service, race_id, checkpoint.frame_index)
    return next(e["driver_id"] for e in snap["predictions"]
                if e["observable"] and e["winner_probability"] is not None)


def _observable_at_both(replay_service, race_id, index):
    """A driver observable with a non-null probability at index-1 and index."""
    assert index >= 1
    checkpoints = _checkpoints(replay_service, race_id)
    first = _snapshot(replay_service, race_id, checkpoints[index - 1].frame_index)
    second = _snapshot(replay_service, race_id, checkpoints[index].frame_index)
    second_ok = {e["driver_id"] for e in second["predictions"]
                 if e["observable"] and e["winner_probability"] is not None}
    for entry in first["predictions"]:
        if entry["driver_id"] in second_ok and entry["observable"] and \
                entry["winner_probability"] is not None:
            return entry["driver_id"]
    pytest.skip("no driver observable at both checkpoints")


def _domain_pair(explanation_service, replay_service, race_id, driver_id,
                 index):
    checkpoints = _checkpoints(replay_service, race_id)
    from_frame = checkpoints[index - 1].frame_index
    to_frame = checkpoints[index].frame_index
    return (
        explanation_service.get_domain_explanation(
            race_id, from_frame, driver_id),
        explanation_service.get_domain_explanation(
            race_id, to_frame, driver_id),
    )


# ---------------------------------------------------------------------------
# PART A — contract + frozen identity
# ---------------------------------------------------------------------------

def test_contract_version_and_semantics():
    assert E5.TIMELINE_EXPLANATION_CONTRACT_VERSION == "v1"
    assert E5.TIMELINE_EXPLANATION_FORMAT == "timeline-explanation-v1"
    assert E5.EXPLANATION_SPACE == "LOG_ODDS"
    assert E5.PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"
    assert E5.LOGIT_ABS_TOL <= 1e-12
    assert E5.PROBABILITY_ABS_TOL <= 1e-12
    assert E5.TOP_N == 5


def test_contract_is_additive_versions_untouched():
    from v2.local_explainability import LOCAL_EXPLANATION_CONTRACT_VERSION
    from v2.replay_predictions import (
        ARTIFACT_FORMAT,
        REPLAY_PREDICTION_CONTRACT_VERSION,
    )
    assert E4.LOCAL_EXPLANATION_CONTRACT_VERSION == "v1"
    assert LOCAL_EXPLANATION_CONTRACT_VERSION == "v1"
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert ARTIFACT_FORMAT == "replay-checkpoints-v1"
    assert E5.TIMELINE_EXPLANATION_FORMAT != ARTIFACT_FORMAT
    source = (ROOT / "v2" / "timeline_explainability.py").read_text()
    assert "replay_predictions" not in source
    assert "import shap" not in source


def test_model_identity(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 1)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[1].frame_index,
        driver)
    model = payload["model_identity"]
    assert model["feature_set"] == "ALL_84"
    assert model["estimator_class"] == "LogisticRegression"
    assert model["transformed_dim"] == 106
    assert model["canonical_feature_count"] == 84
    assert model["specification_fingerprint"] == SPEC_FINGERPRINT
    assert model["probability_semantics"] == "INDEPENDENT_BINARY"


# ---------------------------------------------------------------------------
# PART B/C/D — previous-checkpoint selection + exact identities
# ---------------------------------------------------------------------------

def test_previous_checkpoint_selection(change_service, replay_service):
    checkpoints = _checkpoints(replay_service, RACE_FULL)
    index = len(checkpoints) - 1
    driver = _observable_at_both(replay_service, RACE_FULL, index)
    payload = change_service.get_change(
        RACE_FULL, checkpoints[index].frame_index, driver)
    assert payload["status"] == "AVAILABLE"
    identity = payload["identity"]
    assert identity["from_frame_index"] == checkpoints[index - 1].frame_index
    assert identity["to_frame_index"] == checkpoints[index].frame_index
    assert identity["from_checkpoint"]["frame_index"] == \
        checkpoints[index - 1].frame_index
    assert identity["to_checkpoint"]["frame_index"] == \
        checkpoints[index].frame_index
    assert identity["from_checkpoint"]["reasons"] == \
        list(checkpoints[index - 1].reasons)
    assert identity["to_checkpoint"]["reasons"] == \
        list(checkpoints[index].reasons)


def test_first_checkpoint_has_no_previous(change_service, replay_service):
    checkpoints = _checkpoints(replay_service, RACE_SMALL)
    driver = _observable_driver(replay_service, RACE_SMALL, 0)
    payload = change_service.get_change(
        RACE_SMALL, checkpoints[0].frame_index, driver)
    assert payload["status"] == "NO_PREVIOUS_CHECKPOINT"
    assert payload["identity"]["from_frame_index"] is None
    assert payload["identity"]["from_checkpoint"] is None
    assert payload["identity"]["to_frame_index"] == checkpoints[0].frame_index
    assert payload["logit_delta"] is None
    assert payload["probability_delta"] is None
    assert payload["top_positive"] == []
    assert payload["top_negative"] == []


def test_from_to_cached_probabilities_exact(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[2].frame_index,
        driver)
    assert payload["cached_from_probability"] == pytest.approx(
        payload["from_probability"], abs=E5.PROBABILITY_ABS_TOL)
    assert payload["cached_to_probability"] == pytest.approx(
        payload["to_probability"], abs=E5.PROBABILITY_ABS_TOL)


def test_probability_delta(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 3)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[3].frame_index,
        driver)
    assert payload["probability_delta"] == pytest.approx(
        payload["to_probability"] - payload["from_probability"],
        abs=E5.PROBABILITY_ABS_TOL)


def test_logit_delta(change_service, replay_service, explanation_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[2].frame_index,
        driver)
    assert payload["from_logit"] == pytest.approx(
        from_domain["logit"], abs=E5.LOGIT_ABS_TOL)
    assert payload["to_logit"] == pytest.approx(
        to_domain["logit"], abs=E5.LOGIT_ABS_TOL)
    assert payload["logit_delta"] == pytest.approx(
        to_domain["logit"] - from_domain["logit"], abs=E5.LOGIT_ABS_TOL)


# ---------------------------------------------------------------------------
# PART C — exact delta decomposition
# ---------------------------------------------------------------------------

def test_84_canonical_deltas(explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    rows = payload["canonical_deltas"]
    assert len(rows) == 84
    assert [r["canonical_feature"] for r in rows] == \
        list(explanation_service._predictor.feature_names)
    assert len({r["canonical_feature"] for r in rows}) == 84


def test_canonical_delta_equals_contribution_difference(
        explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    from_by = {r["canonical_feature"]: r["log_odds_contribution"]
               for r in from_domain["canonical_contributions"]}
    to_by = {r["canonical_feature"]: r["log_odds_contribution"]
             for r in to_domain["canonical_contributions"]}
    for row in payload["canonical_deltas"]:
        assert row["contribution_delta"] == pytest.approx(
            to_by[row["canonical_feature"]] - from_by[row["canonical_feature"]],
            abs=E5.LOGIT_ABS_TOL)
        assert row["from_contribution"] == pytest.approx(
            from_by[row["canonical_feature"]], abs=E5.LOGIT_ABS_TOL)
        assert row["to_contribution"] == pytest.approx(
            to_by[row["canonical_feature"]], abs=E5.LOGIT_ABS_TOL)


def test_exact_delta_reconstruction(explanation_service, replay_service):
    for index in (1, 2, 3):
        driver = _observable_at_both(replay_service, RACE_FULL, index)
        from_domain, to_domain = _domain_pair(
            explanation_service, replay_service, RACE_FULL, driver, index)
        payload = E5.explain_prediction_change(from_domain, to_domain)
        delta_sum = sum(r["contribution_delta"]
                        for r in payload["canonical_deltas"])
        assert delta_sum == pytest.approx(
            payload["logit_delta"], abs=E5.LOGIT_ABS_TOL)
        assert payload["reconstruction"]["residual"] == pytest.approx(
            0.0, abs=E5.LOGIT_ABS_TOL)
        assert payload["reconstruction"]["intercept_cancels"] is True


def test_intercept_cancels(explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    assert from_domain["intercept"] == to_domain["intercept"]
    payload = E5.explain_prediction_change(from_domain, to_domain)
    assert payload["reconstruction"]["intercept_cancels"] is True
    assert payload["logit_delta"] == pytest.approx(
        payload["reconstruction"]["canonical_delta_sum"], abs=E5.LOGIT_ABS_TOL)


def test_three_way_probability_consistency(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 3)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[3].frame_index,
        driver)
    assert payload["from_probability"] == pytest.approx(
        payload["cached_from_probability"], abs=E5.PROBABILITY_ABS_TOL)
    assert payload["to_probability"] == pytest.approx(
        payload["cached_to_probability"], abs=E5.PROBABILITY_ABS_TOL)
    assert payload["logit_delta"] == pytest.approx(
        payload["reconstruction"]["canonical_delta_sum"],
        abs=E5.LOGIT_ABS_TOL)


# ---------------------------------------------------------------------------
# PART D/E/F — raw change, categorical + missingness transitions
# ---------------------------------------------------------------------------

def _row_payload(explanation_service, replay_service, race_id, index,
                 driver_id, mutate=None, *, frame_offset=0):
    checkpoint = _checkpoints(replay_service, race_id)[index]
    snap = _snapshot(replay_service, race_id, checkpoint.frame_index)
    entry = _entry(snap, driver_id)
    row = explanation_service._resolve_exact_row(
        race_id, driver_id, int(entry["observed_lap_number"]),
        float(entry["observed_time_s"]))
    if mutate is not None:
        mutate(row)
        cached_probability = None
    else:
        cached_probability = float(entry["winner_probability"])
    identity = LocalExplanationIdentity(
        race_id=race_id, frame_index=checkpoint.frame_index + frame_offset,
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
        explanation_service._predictor, row, identity,
        cached_probability=cached_probability,
        map_entries=explanation_service._map_entries)


def _delta_row(payload, feature):
    return next(r for r in payload["canonical_deltas"]
                if r["canonical_feature"] == feature)


def test_categorical_transition_grouped(
        explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)
    base = _row_payload(explanation_service, replay_service, RACE_FULL, 2,
                        driver)

    def to_hard(row):
        row.iloc[0, row.columns.get_loc("compound")] = "HARD"

    mutated = _row_payload(explanation_service, replay_service, RACE_FULL, 2,
                           driver, to_hard, frame_offset=1)
    result = E5.explain_prediction_change(base, mutated)
    row = _delta_row(result, "compound")
    assert row["feature_type"] == "categorical"
    assert row["contribution_delta"] == pytest.approx(
        row["to_contribution"] - row["from_contribution"],
        abs=E5.LOGIT_ABS_TOL)
    assert result["logit_delta"] == pytest.approx(
        sum(r["contribution_delta"] for r in result["canonical_deltas"]),
        abs=E5.LOGIT_ABS_TOL)


def test_categorical_medium_to_hard_or_same(explanation_service,
                                            replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)
    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver)

    def mutate(row):
        row.iloc[0, row.columns.get_loc("compound")] = "HARD"

    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     mutate, frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, "compound")
    if row["transition"] == E5.TRANSITION_UNCHANGED:
        assert row["contribution_delta"] == pytest.approx(
            0.0, abs=E5.LOGIT_ABS_TOL)
    else:
        assert row["transition"] == E5.TRANSITION_CATEGORICAL
        base_row = next(r for r in a["canonical_contributions"]
                        if r["canonical_feature"] == "compound")
        assert row["from_active_category"] == \
            base_row["active_category"]
        assert row["to_active_category"] == "HARD"


def test_missing_categorical_transition(explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)
    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver)

    def to_missing(row):
        row.iloc[0, row.columns.get_loc("compound")] = np.nan

    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     to_missing, frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, "compound")
    if row["transition"] == E5.TRANSITION_UNCHANGED:
        pytest.skip("compound already missing at this checkpoint")
    assert row["transition"] == E5.TRANSITION_MISSINGNESS
    assert row["to_input_state"] == E4.MISSING_CATEGORY


def test_imputation_transition(explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)

    def to_missing(row):
        row.iloc[0, row.columns.get_loc("position")] = np.nan

    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver)
    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     to_missing, frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, "position")
    assert row["to_input_state"] == E4.IMPUTED_NUMERIC_MEDIAN
    assert row["from_input_state"] == E4.OBSERVED
    assert row["transition"] == E5.TRANSITION_IMPUTATION
    assert row["to_raw_value"] is None
    assert row["to_imputed_value"] is not None


def test_missing_to_observed_transition(explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)

    def to_missing(row):
        row.iloc[0, row.columns.get_loc("position")] = np.nan

    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     to_missing)
    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, "position")
    assert row["transition"] == E5.TRANSITION_IMPUTATION
    assert row["from_raw_value"] is None
    assert row["to_raw_value"] is not None


def test_boolean_change_classified(explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)
    boolean = list(explanation_service._predictor._preprocessor.boolean_columns)
    feature = boolean[0]
    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver)

    def mutate(row):
        current = bool(row.iloc[0, row.columns.get_loc(feature)])
        row.iloc[0, row.columns.get_loc(feature)] = not current

    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     mutate, frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, feature)
    assert row["feature_type"] == "boolean"
    assert row["transition"] in (E5.TRANSITION_INPUT_CHANGED,
                                 E5.TRANSITION_UNCHANGED)


def test_unknown_category_classified(explanation_service, replay_service):
    driver = _observable_driver(replay_service, RACE_FULL, 2)
    a = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver)

    def mutate(row):
        row.iloc[0, row.columns.get_loc("compound")] = "SUPER_HYPER_SOFT"

    b = _row_payload(explanation_service, replay_service, RACE_FULL, 2, driver,
                     mutate, frame_offset=1)
    result = E5.explain_prediction_change(a, b)
    row = _delta_row(result, "compound")
    if row["transition"] == E5.TRANSITION_UNCHANGED:
        pytest.skip("compound already unknown-ish")
    assert row["to_input_state"] == E4.UNKNOWN_CATEGORY
    assert row["transition"] == E5.TRANSITION_MISSINGNESS


# ---------------------------------------------------------------------------
# PART G — top-N policy, accounting, zero / cancellation
# ---------------------------------------------------------------------------

def test_top_positive_and_negative_ordering(explanation_service,
                                            replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    positive = payload["top_positive"]
    negative = payload["top_negative"]
    assert len(positive) <= E5.TOP_N
    assert len(negative) <= E5.TOP_N
    assert all(r["contribution_delta"] > 0 for r in positive)
    assert all(r["contribution_delta"] < 0 for r in negative)
    assert positive == sorted(
        positive, key=lambda r: (-r["contribution_delta"],
                                 r["canonical_feature"]))
    assert negative == sorted(
        negative, key=lambda r: (r["contribution_delta"],
                                 r["canonical_feature"]))


def test_top_tie_break_is_canonical_name():
    rows = [
        {"canonical_feature": "c", "contribution_delta": 0.5},
        {"canonical_feature": "a", "contribution_delta": 0.5},
        {"canonical_feature": "b", "contribution_delta": 0.5},
        {"canonical_feature": "d", "contribution_delta": -0.5},
        {"canonical_feature": "e", "contribution_delta": -0.5},
    ]
    top, _ = E5._top_delta_entries(rows, True, 2)
    assert [r["canonical_feature"] for r in top] == ["a", "b"]
    neg, _ = E5._top_delta_entries(rows, False, 2)
    assert [r["canonical_feature"] for r in neg] == ["d", "e"]


def test_omitted_delta_accounting(explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    acc = payload["accounting"]
    assert acc["shown_positive_log_odds_delta"] + \
        acc["omitted_positive_log_odds_delta"] == pytest.approx(
            acc["total_positive_log_odds_delta"], abs=E5.LOGIT_ABS_TOL)
    assert acc["shown_negative_log_odds_delta"] + \
        acc["omitted_negative_log_odds_delta"] == pytest.approx(
            acc["total_negative_log_odds_delta"], abs=E5.LOGIT_ABS_TOL)
    assert acc["total_positive_log_odds_delta"] + \
        acc["total_negative_log_odds_delta"] == pytest.approx(
            payload["logit_delta"], abs=E5.LOGIT_ABS_TOL)
    assert acc["omitted_positive_log_odds_delta"] >= 0
    assert acc["omitted_negative_log_odds_delta"] <= 0
    assert acc["top_n_reconstructs_change"] is False
    assert acc["full_decomposition_reconstructs_change"] is True


def _synthetic_row(feature, contribution, *, raw=1.0, ftype="numeric",
                   state="OBSERVED", active=None, imputed=None):
    return {
        "canonical_feature": feature, "feature_family": "F",
        "feature_type": ftype, "raw_value": raw, "input_state": state,
        "imputed_value": imputed, "active_category": active,
        "log_odds_contribution": contribution, "direction": "NEUTRAL"}


def _synthetic_payload(frame, rows):
    logit = float(sum(r["log_odds_contribution"] for r in rows))
    return {
        "contract_version": E4.LOCAL_EXPLANATION_CONTRACT_VERSION,
        "identity": {
            "race_id": "x", "driver_id": "d", "frame_index": frame,
            "checkpoint_reasons": ["LEADER_LAP"], "leader_lap": 1,
            "state_time_s": float(frame), "anchor_driver_id": "d",
            "anchor_lap_number": 1, "anchor_state_time_s": float(frame),
            "observation": {"observed_lap_number": frame,
                            "observed_time_s": float(frame),
                            "observed_position": 1, "observation_age_s": 0.0}},
        "model_identity": {"k": "v"},
        "probability_semantics": "INDEPENDENT_BINARY",
        "explanation_space": "LOG_ODDS",
        "logit": logit, "probability": E4._sigmoid(logit),
        "cached_probability": E4._sigmoid(logit),
        "canonical_feature_count": len(rows),
        "canonical_contributions": rows,
        "top_positive": [], "top_negative": [], "accounting": {}}


def test_zero_delta_case():
    a = _synthetic_payload(0, [_synthetic_row("x", 0.7),
                               _synthetic_row("y", -0.2)])
    b = copy.deepcopy(a)
    b["identity"]["frame_index"] = 5
    payload = E5.explain_prediction_change(a, b)
    assert payload["logit_delta"] == pytest.approx(0.0, abs=E5.LOGIT_ABS_TOL)
    assert payload["probability_delta"] == pytest.approx(
        0.0, abs=E5.PROBABILITY_ABS_TOL)
    assert payload["top_positive"] == []
    assert payload["top_negative"] == []
    assert payload["accounting"]["total_positive_log_odds_delta"] == 0.0
    assert payload["accounting"]["total_negative_log_odds_delta"] == 0.0
    for row in payload["canonical_deltas"]:
        assert row["contribution_delta"] == 0.0
        assert row["transition"] == E5.TRANSITION_UNCHANGED


def test_positive_negative_cancellation():
    a = _synthetic_payload(0, [_synthetic_row("x", 0.0),
                               _synthetic_row("y", 0.0)])
    b = _synthetic_payload(5, [_synthetic_row("x", 1.0),
                               _synthetic_row("y", -1.0)])
    payload = E5.explain_prediction_change(a, b)
    assert payload["logit_delta"] == pytest.approx(0.0, abs=E5.LOGIT_ABS_TOL)
    assert payload["accounting"]["total_positive_log_odds_delta"] == \
        pytest.approx(1.0, abs=E5.LOGIT_ABS_TOL)
    assert payload["accounting"]["total_negative_log_odds_delta"] == \
        pytest.approx(-1.0, abs=E5.LOGIT_ABS_TOL)
    assert payload["accounting"]["total_positive_log_odds_delta"] + \
        payload["accounting"]["total_negative_log_odds_delta"] == \
        pytest.approx(payload["logit_delta"], abs=E5.LOGIT_ABS_TOL)


def test_public_projection_is_compact(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    payload = change_service.get_change(
        RACE_FULL, _checkpoints(replay_service, RACE_FULL)[2].frame_index,
        driver)
    assert "canonical_deltas" not in payload
    assert len(payload["top_positive"]) <= E5.TOP_N
    assert len(payload["top_negative"]) <= E5.TOP_N
    for key in ("contract_version", "status", "identity", "from_probability",
                "to_probability", "probability_delta", "from_logit",
                "to_logit", "logit_delta", "accounting", "reconstruction"):
        assert key in payload


def test_no_probability_normalization(explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    joined = json.dumps(E5.public_change_explanation(payload)).lower()
    for bad in ("probabilities normalized", "probability share",
                "vote share", "softmax"):
        assert bad not in joined
    assert payload["probability_semantics"] == "INDEPENDENT_BINARY"


# ---------------------------------------------------------------------------
# Firewalls + red team
# ---------------------------------------------------------------------------

def test_2025_firewall(change_service):
    with pytest.raises(RaceNotFoundError):
        change_service.get_change("2025-r01-R", 0, "verstappen")


def test_label_firewall_matrix_columns(stack):
    forbidden = {"is_winner", "final_position", "classified_flag",
                 "eligible_is_winner", "eligible_is_podium",
                 "eligible_scored_points"}
    assert not (set(stack.matrix._frame.columns) & forbidden)
    assert set(stack.matrix._frame.columns) == (
        set(stack.matrix.feature_names) | set(IDENTITY_COLUMNS)
        | {"season"})


def test_classified_flag_and_labels_not_consumed():
    source = (ROOT / "v2" / "timeline_explainability.py").read_text()
    for token in ("is_winner", "classified_flag", "eligible_is_winner",
                  "read_parquet", "final_position"):
        assert token not in source


def test_non_checkpoint_fails_closed(change_service, replay_service):
    series = replay_service.get_series(RACE_SMALL)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(0, 30) if i not in hits)
    with pytest.raises(NotPredictionCheckpointError):
        change_service.get_change(RACE_SMALL, plain, "hamilton")


def test_unknown_driver_fails_closed(change_service, replay_service):
    checkpoint = _checkpoints(replay_service, RACE_FULL)[1]
    with pytest.raises(UnknownDriverError):
        change_service.get_change(
            RACE_FULL, checkpoint.frame_index, "not_a_real_driver")


def test_driver_unobservable_state(change_service, replay_service):
    """An unobservable endpoint yields an explicit COMPARISON_UNAVAILABLE."""
    victim = None
    victim_race = victim_frame = None
    for race_id in (RACE_FULL, RACE_SMALL):
        checkpoints = _checkpoints(replay_service, race_id)
        for index in range(1, len(checkpoints)):
            a = _snapshot(replay_service, race_id,
                          checkpoints[index - 1].frame_index)
            b = _snapshot(replay_service, race_id,
                          checkpoints[index].frame_index)
            roster = [e["driver_id"] for e in b["predictions"]]
            for driver in roster:
                ea = _entry(a, driver)
                eb = _entry(b, driver)
                if ea is None or eb is None:
                    continue
                if (not eb["observable"] or
                        eb["winner_probability"] is None or
                        not ea["observable"] or
                        ea["winner_probability"] is None):
                    victim = driver
                    victim_race = race_id
                    victim_frame = checkpoints[index].frame_index
                    break
            if victim is not None:
                break
        if victim is not None:
            break
    if victim is None:
        pytest.skip("no endpoint-unobservable driver in the local corpus")
    payload = change_service.get_change(victim_race, victim_frame, victim)
    assert payload["status"] == "COMPARISON_UNAVAILABLE"
    assert payload["reason"] in (
        E5.REASON_DRIVER_NOT_OBSERVABLE_AT_PREVIOUS,
        E5.REASON_NULL_PROBABILITY_AT_PREVIOUS,
        E5.REASON_DRIVER_NOT_OBSERVABLE_AT_SELECTED,
        E5.REASON_NULL_PROBABILITY_AT_SELECTED)
    assert payload["logit_delta"] is None
    assert payload["from_probability"] is None


def test_unavailable_reason_null_probability():
    entry_ok = {"observable": True, "winner_probability": 0.3}
    entry_null = {"observable": True, "winner_probability": None}
    entry_unobs = {"observable": False, "winner_probability": None}
    assert V2TimelineExplanationService._unavailable_reason(
        entry_null, entry_ok) == E5.REASON_NULL_PROBABILITY_AT_PREVIOUS
    assert V2TimelineExplanationService._unavailable_reason(
        entry_ok, entry_null) == E5.REASON_NULL_PROBABILITY_AT_SELECTED
    assert V2TimelineExplanationService._unavailable_reason(
        entry_unobs, entry_ok) == \
        E5.REASON_DRIVER_NOT_OBSERVABLE_AT_PREVIOUS
    assert V2TimelineExplanationService._unavailable_reason(
        entry_ok, entry_unobs) == \
        E5.REASON_DRIVER_NOT_OBSERVABLE_AT_SELECTED
    assert V2TimelineExplanationService._unavailable_reason(
        None, entry_ok) == E5.REASON_DRIVER_ABSENT_AT_PREVIOUS
    assert V2TimelineExplanationService._unavailable_reason(
        entry_ok, entry_ok) is None


def test_service_comparison_unavailable_null_probability(
        explanation_service):
    """Deterministic COMPARISON_UNAVAILABLE when A carries a null probability."""
    class _StubReplay(V2ReplayService):
        def __init__(self, snaps, frames):
            self._snaps = snaps
            self._frames = frames

        def get_prediction(self, race_id, frame_index):
            return self._snaps[frame_index]

        def get_series(self, race_id):
            return SimpleNamespace(checkpoints=[
                SimpleNamespace(frame_index=f) for f in self._frames])

    def checkpoint(frame):
        return {"frame_index": frame, "reasons": ["LEADER_LAP"],
                "leader_lap": 1, "anchor_driver_id": "d",
                "anchor_lap_number": frame, "anchor_state_time_s": float(frame)}

    def entry(prob):
        return {"driver_id": "d", "observable": True,
                "winner_probability": prob, "observed_lap_number": 1,
                "observed_time_s": 1.0, "observed_position": 1,
                "observation_age_s": 0.0}

    def snapshot(frame, prob):
        return {"state_time_s": float(frame), "anchor_driver_id": "d",
                "anchor_lap_number": frame, "predictions": [entry(prob)]}

    stub = _StubReplay.__new__(_StubReplay)
    _StubReplay.__init__(stub, {
        10: {"checkpoint": checkpoint(10), "prediction": snapshot(10, None)},
        20: {"checkpoint": checkpoint(20), "prediction": snapshot(20, 0.4)},
    }, [10, 20])
    service = V2TimelineExplanationService(stub, explanation_service)
    payload = service.get_change("2026-x", 20, "d")
    assert payload["status"] == "COMPARISON_UNAVAILABLE"
    assert payload["reason"] == E5.REASON_NULL_PROBABILITY_AT_PREVIOUS
    assert payload["identity"]["from_frame_index"] == 10

    one = _StubReplay.__new__(_StubReplay)
    _StubReplay.__init__(one, {
        5: {"checkpoint": checkpoint(5), "prediction": snapshot(5, 0.4)}}, [5])
    only = V2TimelineExplanationService(one, explanation_service)
    assert only.get_change("2026-x", 5, "d")["status"] == \
        E5.STATUS_NO_PREVIOUS_CHECKPOINT


def test_feature_order_tamper_fails_closed(explanation_service,
                                           replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    tampered = copy.deepcopy(to_domain)
    tampered["canonical_contributions"] = (
        tampered["canonical_contributions"][1:]
        + tampered["canonical_contributions"][:1])
    with pytest.raises(E5.ChangeIdentityError):
        E5.explain_prediction_change(from_domain, tampered)


def test_altered_cached_probability_fails_closed(explanation_service,
                                                 replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    tampered = copy.deepcopy(to_domain)
    tampered["cached_probability"] = \
        float(tampered["cached_probability"]) + 0.1
    with pytest.raises(E5.ChangeIdentityError):
        E5.explain_prediction_change(from_domain, tampered)


def test_same_frame_change_fails_closed():
    a = _synthetic_payload(3, [_synthetic_row("x", 0.7)])
    with pytest.raises(E5.ChangeIdentityError):
        E5.explain_prediction_change(a, a)


def test_language_contract(explanation_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    from_domain, to_domain = _domain_pair(
        explanation_service, replay_service, RACE_FULL, driver, 2)
    payload = E5.explain_prediction_change(from_domain, to_domain)
    E3.assert_language_compliant(
        payload, forbidden=E5.TIMELINE_FORBIDDEN_LANGUAGE)
    assert payload["language_contract"]["forbidden"]
    for text in ("the pit stop caused the increase",
                 "this is the reason probability changed",
                 "the model reacted to the overtake",
                 "it made the driver more likely to win",
                 "gap added 12 probability points",
                 "the model log-odds increased because of the tyre change"):
        with pytest.raises(E3.ExplainabilityError):
            E3.assert_language_compliant(
                {"note": text}, forbidden=E5.TIMELINE_FORBIDDEN_LANGUAGE)


def test_no_shap_or_llm_in_module():
    source = (ROOT / "v2" / "timeline_explainability.py").read_text()
    assert "import shap" not in source
    assert "openai" not in source
    assert "anthropic" not in source


def test_post_b_mutation_invariance(explanation_service, replay_service,
                                    stack):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    checkpoints = _checkpoints(replay_service, RACE_FULL)
    from_frame = checkpoints[1].frame_index
    to_frame = checkpoints[2].frame_index
    from_domain = explanation_service.get_domain_explanation(
        RACE_FULL, from_frame, driver)
    to_domain = explanation_service.get_domain_explanation(
        RACE_FULL, to_frame, driver)
    baseline = E5.explain_prediction_change(from_domain, to_domain)

    # Mutate every matrix row strictly after the selected observation of B.
    to_entry = _entry(
        _snapshot(replay_service, RACE_FULL, to_frame), driver)
    cutoff = float(to_entry["observed_time_s"])
    mutated = stack.matrix._frame.copy()
    future = mutated["state_time_s"] > cutoff + 1e-9
    assert future.any()
    for name in stack.matrix.feature_names:
        dtype = mutated[name].dtype.kind
        if dtype == "b":
            mutated.loc[future, name] = True
        elif dtype in "iu":
            mutated.loc[future, name] = 999999
        elif dtype == "f":
            mutated.loc[future, name] = 999999.0
        else:
            mutated.loc[future, name] = "MUTATED"
    backend = FrozenReplayFeatureMatrix(
        mutated, stack.matrix.feature_names, stack.matrix.manifest_record)
    mutated_from = _domain_from_backend(
        explanation_service, backend, RACE_FULL, from_frame, driver)
    mutated_to = _domain_from_backend(
        explanation_service, backend, RACE_FULL, to_frame, driver)
    mutated_change = E5.explain_prediction_change(mutated_from, mutated_to)
    assert _render(mutated_change) == _render(baseline)


def test_between_rows_mutation_invariance(explanation_service,
                                          replay_service, stack):
    """Rows between A and B (not the exact A/B rows) never move A or B."""
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    checkpoints = _checkpoints(replay_service, RACE_FULL)
    from_frame = checkpoints[1].frame_index
    to_frame = checkpoints[2].frame_index
    baseline = E5.explain_prediction_change(
        explanation_service.get_domain_explanation(
            RACE_FULL, from_frame, driver),
        explanation_service.get_domain_explanation(
            RACE_FULL, to_frame, driver))

    a_entry = _entry(_snapshot(replay_service, RACE_FULL, from_frame), driver)
    b_entry = _entry(_snapshot(replay_service, RACE_FULL, to_frame), driver)
    a_time = float(a_entry["observed_time_s"])
    b_time = float(b_entry["observed_time_s"])
    mutated = stack.matrix._frame.copy()
    between = (mutated["state_time_s"] > a_time + 1e-9) & \
        (mutated["state_time_s"] < b_time - 1e-9)
    for name in stack.matrix.feature_names:
        dtype = mutated[name].dtype.kind
        if dtype == "b":
            mutated.loc[between, name] = True
        elif dtype in "iu":
            mutated.loc[between, name] = 999999
        elif dtype == "f":
            mutated.loc[between, name] = 999999.0
        else:
            mutated.loc[between, name] = "MUTATED"
    backend = FrozenReplayFeatureMatrix(
        mutated, stack.matrix.feature_names, stack.matrix.manifest_record)
    mutated_change = E5.explain_prediction_change(
        _domain_from_backend(explanation_service, backend, RACE_FULL,
                             from_frame, driver),
        _domain_from_backend(explanation_service, backend, RACE_FULL,
                             to_frame, driver))
    assert _render(mutated_change) == _render(baseline)


def _domain_from_backend(explanation_service, backend, race_id, frame_index,
                         driver_id):
    snap = explanation_service._replay.get_prediction(
        race_id, frame_index)["prediction"]
    checkpoint = explanation_service._replay.get_prediction(
        race_id, frame_index)["checkpoint"]
    entry = _entry(snap, driver_id)
    requests = pd.DataFrame(
        [[race_id, driver_id, int(entry["observed_lap_number"]),
          float(entry["observed_time_s"])]],
        columns=list(IDENTITY_COLUMNS))
    joined = backend.lookup(requests, backend.race_slice(race_id))
    row = joined.iloc[[0]][list(explanation_service._predictor.feature_names)]
    identity = LocalExplanationIdentity(
        race_id=race_id, frame_index=int(frame_index), driver_id=driver_id,
        observed_lap_number=int(entry["observed_lap_number"]),
        observed_time_s=float(entry["observed_time_s"]),
        state_time_s=float(snap["state_time_s"]),
        anchor_driver_id=str(snap["anchor_driver_id"]),
        anchor_lap_number=int(snap["anchor_lap_number"]),
        anchor_state_time_s=float(snap["state_time_s"]),
        checkpoint_reasons=tuple(checkpoint["reasons"]),
        leader_lap=checkpoint["leader_lap"],
        observed_position=entry["observed_position"],
        observation_age_s=entry["observation_age_s"])
    return E4.explain_winner_prediction(
        explanation_service._predictor, row, identity,
        cached_probability=float(entry["winner_probability"]),
        map_entries=explanation_service._map_entries)


def _render(payload):
    return json.dumps(payload, sort_keys=True)


def test_determinism(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_FULL, 2)
    frame = _checkpoints(replay_service, RACE_FULL)[2].frame_index
    first = change_service.get_change(RACE_FULL, frame, driver)
    second = change_service.get_change(RACE_FULL, frame, driver)
    assert _render(first) == _render(second)


# ---------------------------------------------------------------------------
# API endpoint semantics
# ---------------------------------------------------------------------------

def _client(change_service):
    from fastapi.testclient import TestClient
    from api.main import app
    app.dependency_overrides[get_v2_timeline_explanation_service] = \
        lambda: change_service
    return TestClient(app, raise_server_exceptions=False)


def _route(race_id, frame_index, driver_id):
    return (f"/v2/replay/{race_id}/frames/{frame_index}"
            f"/predictions/{driver_id}/change")


def _clear_override():
    from api.main import app
    app.dependency_overrides.pop(
        get_v2_timeline_explanation_service, None)


def test_api_available(change_service, replay_service):
    driver = _observable_at_both(replay_service, RACE_SMALL, 1)
    frame = _checkpoints(replay_service, RACE_SMALL)[1].frame_index
    client = _client(change_service)
    try:
        resp = client.get(_route(RACE_SMALL, frame, driver))
    finally:
        _clear_override()
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "AVAILABLE"
    assert body["explanation_space"] == "LOG_ODDS"
    assert body["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["identity"]["driver_id"] == driver
    assert body["accounting"]["top_n_reconstructs_change"] is False
    E3.assert_language_compliant(
        json.loads(resp.text), forbidden=E5.TIMELINE_FORBIDDEN_LANGUAGE)


def test_api_no_previous_checkpoint(change_service, replay_service):
    driver = _observable_driver(replay_service, RACE_SMALL, 0)
    frame = _checkpoints(replay_service, RACE_SMALL)[0].frame_index
    client = _client(change_service)
    try:
        resp = client.get(_route(RACE_SMALL, frame, driver))
    finally:
        _clear_override()
    assert resp.status_code == 200
    assert resp.json()["status"] == "NO_PREVIOUS_CHECKPOINT"


def test_api_unknown_driver(change_service, replay_service):
    frame = _checkpoints(replay_service, RACE_SMALL)[1].frame_index
    client = _client(change_service)
    try:
        resp = client.get(_route(RACE_SMALL, frame, "not_a_real_driver"))
    finally:
        _clear_override()
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_driver"


def test_api_non_checkpoint(change_service, replay_service):
    series = replay_service.get_series(RACE_SMALL)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(0, 30) if i not in hits)
    client = _client(change_service)
    try:
        resp = client.get(_route(RACE_SMALL, plain, "hamilton"))
    finally:
        _clear_override()
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_prediction_checkpoint"
    assert body["previous_prediction_checkpoint_frame"] is not None or \
        body["next_prediction_checkpoint_frame"] is not None


def test_api_unknown_race_and_2025(change_service):
    client = _client(change_service)
    try:
        assert client.get(_route("nope", 0, "hamilton")).status_code == 404
        resp = client.get(_route("2025-r01-R", 0, "hamilton"))
    finally:
        _clear_override()
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_api_cache_missing_503(stack, replay_service, explanation_service):
    import tempfile
    empty = V2ReplayService(
        stack.states, stack.recon, [r for _, r in RACES],
        checkpoints_dir=tempfile.mkdtemp(),
        scientific_inputs=dict(stack.scientific))
    empty_explanations = V2ExplanationService(
        empty, stack.predictor, stack.matrix, map_entries=stack.map_entries)
    empty_changes = V2TimelineExplanationService(empty, empty_explanations)
    checkpoint = empty.get_series(RACE_SMALL).checkpoints[0]
    snap = replay_service.get_prediction(
        RACE_SMALL, checkpoint.frame_index)["prediction"]
    driver = next(e["driver_id"] for e in snap["predictions"]
                  if e["observable"])
    client = _client(empty_changes)
    try:
        resp = client.get(_route(RACE_SMALL, checkpoint.frame_index, driver))
    finally:
        _clear_override()
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_missing"


def test_api_route_inventory_additive(change_service):
    client = _client(change_service)
    try:
        paths = client.get("/openapi.json").json()["paths"]
    finally:
        _clear_override()
    assert ("/v2/replay/{race_id}/frames/{frame_index}/predictions/"
            "{driver_id}/change") in paths
    assert ("/v2/replay/{race_id}/frames/{frame_index}/predictions/"
            "{driver_id}/explanation") in paths


# ---------------------------------------------------------------------------
# PART R — performance (on-demand; characterizes whether a cache is needed)
# ---------------------------------------------------------------------------

def test_change_latency_characterized(change_service, replay_service, capsys):
    checkpoints = _checkpoints(replay_service, RACE_FULL)
    indices = [1, len(checkpoints) // 2, len(checkpoints) - 1]
    latencies = []
    for index in indices:
        driver = _observable_at_both(replay_service, RACE_FULL, index)
        for _ in range(10):
            started = time.perf_counter()
            change_service.get_change(
                RACE_FULL, checkpoints[index].frame_index, driver)
            latencies.append((time.perf_counter() - started) * 1000)
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
    with capsys.disabled():
        print(f"\n[E5-perf] n={len(latencies)} p50={p50:.1f}ms "
              f"p95={p95:.1f}ms max={latencies[-1]:.1f}ms")
    assert p95 < 500.0  # comfortably interactive even on a slow runner
