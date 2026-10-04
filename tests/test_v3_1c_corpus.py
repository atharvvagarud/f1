"""V3.1C corpus tests (Tier-3 only; need matrix + sidecar).

Pinned in scripts/ci_corpus_dependent.txt; never runs in normal source
CI. Recomputes (never trusts) the V3.1C gates on D1: Arm A fidelity vs
the stored M7 outer result, A/B/C population equality, prediction
determinism, and the 2025 firewall on real artifacts. No 2025 data is
touched; no model performance beyond D1 diagnostics is inspected.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from raceintel.model_lab import v3_dynamics_experiment as V3

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def frames():
    return V3.load_joined_frame(str(ROOT))


@pytest.fixture(scope="module")
def names_84():
    return V3.v3_feature_names(V3.ARM_A)


def _m7_outer(fold):
    report = json.loads(
        (ROOT / "data/v2/model_lab/reports/"
         "logreg_boundary_resolution_v1.json").read_text())
    dest = report["per_fold"][fold]["outer"]["dest"].split(
        "protocol=v1/")[-1]
    return json.loads(
        (ROOT / "data/v2/model_lab/experiments/protocol=v1"
         / dest / "result.json").read_text())


def test_arm_a_fidelity_d1_per_race(frames, names_84):
    augmented, plain = frames
    out = V3.run_v3_arm(augmented, plain, "D1", V3.ARM_A, names_84,
                        model_c=0.003)
    stored = _m7_outer("D1")
    got_map = out["metrics"]["log_loss"]["race_macro"]["per_race"]
    want_map = stored["metrics"]["log_loss"]["race_macro"]["per_race"]
    assert set(got_map) == set(want_map)
    worst = max(abs(float(got_map[r]) - float(want_map[r]))
                for r in got_map)
    assert worst <= 1e-9
    assert abs(float(out["metrics"]["log_loss"]["race_macro"]["value"])
               - float(stored["metrics"]["log_loss"]["race_macro"]
                       ["value"])) <= 1e-9


def test_population_equality_d1(frames, names_84):
    augmented, plain = frames
    names_core = V3.v3_feature_names(V3.ARM_C)
    names_110 = V3.v3_feature_names(V3.ARM_B, names_84)
    hashes = set()
    for arm, names in ((V3.ARM_A, names_84), (V3.ARM_B, names_110),
                       (V3.ARM_C, names_core)):
        ds = V3.materialize_v3(augmented, "D1", arm, names)
        assert ds.validation_counts["eligible"] == 23577
        hashes.add(tuple(ds.validation_metadata["state_id"]))
    assert len(hashes) == 1  # identical eligible populations A/B/C


def test_prediction_determinism_d1(frames, names_84):
    augmented, plain = frames
    names_110 = V3.v3_feature_names(V3.ARM_B, names_84)
    first = V3.run_v3_arm(augmented, plain, "D1", V3.ARM_B, names_110)
    second = V3.run_v3_arm(augmented, plain, "D1", V3.ARM_B, names_110)
    assert np.array_equal(np.asarray(first["predictions"]),
                          np.asarray(second["predictions"]))
    boot1 = V3.paired_bootstrap(
        first["metrics"]["log_loss"]["race_macro"]["per_race"],
        first["metrics"]["log_loss"]["race_macro"]["per_race"])
    assert boot1["mean_delta"] == 0.0


def test_no_holdout_rows_in_predictions():
    import pandas as pd
    for path in sorted((ROOT / "data/v3/v3_1c").glob("pred_*.parquet")):
        seasons = set(pd.read_parquet(path, columns=["season"])
                      ["season"].tolist())
        assert seasons <= {2022, 2023, 2024}, path
        assert 2025 not in seasons
