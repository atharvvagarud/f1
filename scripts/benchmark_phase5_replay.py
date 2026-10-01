"""Phase-5 R7 replay benchmark (reproducible, model-free).

Measures the R7-Q surfaces over representative canonical fixtures:
service init, timeline cold/warm, timeline HTTP pagination, factual frame
reconstruction (early/mid/late/stale/partial/red/shared-T), frame HTTP,
checkpoint-series selection, cached-prediction artifact load/lookup,
probability projection, probability-timeline HTTP, and leader-lap lookup.

The frozen model is NEVER loaded: cached-prediction surfaces use a
synthetic artifact written to a tempdir (the same shape the frozen engine
stores). Percentiles are only reported when the sample count supports
them (p95 >= 20 samples, p99 >= 100 samples) — never inferred from a
handful of runs.

Usage:
    python scripts/benchmark_phase5_replay.py
    python scripts/benchmark_phase5_replay.py --repeats 40 --json /tmp/r7.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from api.v2_replay_service import V2ReplayService
from api.v2_replay_service import get_v2_replay_service
from raceintel.replay import replay as RP
from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
from raceintel.replay.replay_predictions import (
    build_artifact,
    cache_identity_inputs,
    canonical_data_identity,
    load_validated_artifact,
    select_checkpoints,
    write_artifact,
)
from raceintel.replay.replay_reconstruction import ReplayReconstructor
from raceintel.replay.replay_probability_timeline import build_probability_timeline

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")

#: (season, race_id, role) — representative R7-D fixtures.
FIXTURES = [
    (2023, "2023-r01-R", "ordinary"),
    (2022, "2022-r07-R", "stale"),
    (2021, "2021-r12-R", "partial"),
    (2022, "2022-r18-R", "red"),
    (2020, "2020-r09-R", "shared_t_sc"),
]

SYN_SCI = {
    "feature_set": "ALL_84",
    "feature_set_version": "v8",
    "serving_artifact_sha256": "bench-sha",
    "model_specification_fingerprint": "bench-fp",
    "phase2_content_hash": "bench-phase2",
    "probability_semantics": "INDEPENDENT_BINARY",
}

MODEL_DICT = {
    "task": "winner", "target": "is_winner",
    "eligibility_mask": "eligible_is_winner", "feature_set": "ALL_84",
    "feature_set_version": "v8", "estimator": "LogisticRegression",
    "estimator_params": [["C", 0.01]], "calibration_method": "RAW",
    "probability_semantics": "INDEPENDENT_BINARY",
    "training_seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
    "transformed_dim": 106, "feature_count": 84,
    "artifact_sha256": "bench-sha", "specification_fingerprint": "bench-fp",
    "sklearn_version": "1.8.0",
}


def load_corpus():
    state_parts, result_parts = [], []
    for season, race, _ in FIXTURES:
        frame = pd.read_parquet(D9.format(season=season))
        state_parts.append(frame[frame["race_id"] == race].copy())
        result_parts.append(pd.read_parquet(
            RESULTS.format(season=season, race=race)))
    states = pd.concat(state_parts, ignore_index=True)
    results = pd.concat(result_parts, ignore_index=True)
    return states, RaceStateReconstructor(states, results)


def race_states(states, race_id):
    return states[states["race_id"] == race_id].copy()


def summarize(samples):
    ordered = sorted(samples)
    n = len(ordered)
    out = {
        "n": n,
        "mean_ms": statistics.fmean(ordered) * 1000.0,
        "p50_ms": ordered[n // 2] * 1000.0,
        "min_ms": ordered[0] * 1000.0,
        "max_ms": ordered[-1] * 1000.0,
    }
    out["p95_ms"] = (ordered[min(n - 1, int(round(0.95 * (n - 1))))] * 1000.0
                     if n >= 20 else None)
    out["p99_ms"] = (ordered[min(n - 1, int(round(0.99 * (n - 1))))] * 1000.0
                     if n >= 100 else None)
    return out


def time_call(fn, repeats):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


def make_synthetic_artifact(states, race_id, directory):
    timeline = RP.build_replay_timeline(race_states(states, race_id))
    series = select_checkpoints(timeline, race_states(states, race_id))
    roster = sorted(set(race_states(states, race_id)["driver_id"]))
    snapshots = {}
    for order, checkpoint in enumerate(series.checkpoints):
        entries = []
        for position, driver in enumerate(roster):
            entries.append({
                "driver_id": driver, "observable": True,
                "observed_lap_number": checkpoint.anchor_lap_number,
                "observed_time_s": checkpoint.anchor_state_time_s,
                "observation_age_s": 0.0, "observed_position": position + 1,
                "winner_probability": 0.05 + 0.001 * ((order + position) % 7),
                "unavailable_reason": None})
        snapshots[checkpoint.frame_index] = {
            "race_id": checkpoint.race_id,
            "anchor_driver_id": checkpoint.anchor_driver_id,
            "anchor_lap_number": checkpoint.anchor_lap_number,
            "state_time_s": checkpoint.anchor_state_time_s,
            "roster_size": len(roster), "observable_count": len(roster),
            "unavailable_count": 0,
            "probability_semantics": "INDEPENDENT_BINARY",
            "probability_semantics_note": "benchmark synthetic",
            "feature_set": "ALL_84", "model": dict(MODEL_DICT),
            "predictions": entries}
    inputs = cache_identity_inputs(
        series=series,
        data_identity=canonical_data_identity(
            race_states(states, race_id), race_id),
        feature_set=SYN_SCI["feature_set"],
        feature_set_version=SYN_SCI["feature_set_version"],
        artifact_sha256=SYN_SCI["serving_artifact_sha256"],
        specification_fingerprint=SYN_SCI[
            "model_specification_fingerprint"],
        phase2_content_hash=SYN_SCI["phase2_content_hash"],
        probability_semantics=SYN_SCI["probability_semantics"])
    artifact = build_artifact(series, snapshots, dict(MODEL_DICT), inputs)
    path = os.path.join(directory, f"{race_id}.json")
    write_artifact(path, artifact)
    return path, inputs, series


def run(repeats: int) -> dict:
    states, reconstructor = load_corpus()
    started = time.perf_counter()
    service = V2ReplayService(
        states, reconstructor, [race for _, race, _ in FIXTURES],
        checkpoints_dir=tempfile.mkdtemp(prefix="r7bench-"),
        scientific_inputs=dict(SYN_SCI))
    service_init = time.perf_counter() - started
    results = {"environment": {"python": sys.version.split()[0],
                               "repeats": repeats},
               "service_init_s": service_init}

    ordinary = "2023-r01-R"
    states_ordinary = race_states(states, ordinary)
    resolver = ReplayReconstructor(
        RP.build_replay_timeline(states_ordinary), reconstructor)

    results["timeline_cold_build"] = summarize(
        time_call(lambda: RP.build_replay_timeline(states_ordinary), repeats))
    timeline = service.get_timeline(ordinary)
    results["timeline_warm_lookup"] = summarize(
        time_call(lambda: service.get_timeline(ordinary), repeats))
    results["checkpoint_series_selection"] = summarize(
        time_call(lambda: select_checkpoints(timeline, states_ordinary),
                  repeats))
    mid_frame = timeline.frame_count // 2
    mid_lap = max(1, resolver.leader_lap_at(mid_frame) or 1)
    results["leader_lap_lookup"] = summarize(time_call(
        lambda: resolver.frame_for_leader_lap(mid_lap), repeats))

    # Factual reconstruction across roles (own frame index per role).
    reports = {
        "early": (ordinary, 0),
        "mid": (ordinary, timeline.frame_count // 2),
        "late": (ordinary, timeline.frame_count - 1),
    }
    for season, race_id, role in FIXTURES:
        tl = service.get_timeline(race_id)
        if role == "stale":
            reports["stale"] = (race_id, tl.frame_count // 2)
        elif role == "partial":
            reports["partial"] = (race_id, tl.frame_count - 1)
        elif role == "red":
            reports["red"] = (race_id, _regime_frame(
                states, race_id, tl, {"red_flag"}))
        elif role == "shared_t_sc":
            reports["shared_t"] = (race_id, _frame_near(service, race_id,
                                                        2974.257))
    for role, (race_id, index) in reports.items():
        r = ReplayReconstructor(service.get_timeline(race_id), reconstructor)
        results[f"reconstruct_{role}"] = summarize(
            time_call(lambda r=r, i=index: r.state_at(i), repeats))

    # Cached prediction surfaces (synthetic artifact in a tempdir).
    checkpoint_dir = tempfile.mkdtemp(prefix="r7bench-cache-")
    artifact_path, inputs, series = make_synthetic_artifact(
        states, ordinary, checkpoint_dir)
    results["artifact_load"] = summarize(time_call(
        lambda: load_validated_artifact(
            artifact_path, expected_inputs=inputs, series=series), repeats))
    hit_service = V2ReplayService(
        states, reconstructor, [race for _, race, _ in FIXTURES],
        checkpoints_dir=checkpoint_dir, scientific_inputs=dict(SYN_SCI))
    checkpoint_frame = series.checkpoints[len(series.checkpoints) // 2]
    results["cached_prediction_lookup"] = summarize(time_call(
        lambda: hit_service.get_prediction(
            ordinary, checkpoint_frame.frame_index), repeats))
    artifact = hit_service._load_artifact(ordinary, series)
    results["probability_projection"] = summarize(
        time_call(lambda: build_probability_timeline(artifact), repeats))

    # HTTP surfaces.
    from fastapi.testclient import TestClient

    from api.main import app
    app.dependency_overrides[get_v2_replay_service] = lambda: hit_service
    try:
        client = TestClient(app, raise_server_exceptions=False)
        total = service.get_timeline(ordinary).frame_count

        def paginate():
            offset, limit = 0, 500
            while offset < total:
                page = client.get(
                    f"/v2/races/{ordinary}/replay/timeline",
                    params={"offset": offset, "limit": limit})
                assert page.status_code == 200
                offset += len(page.json()["frames"])

        results["timeline_http_pagination"] = summarize(
            time_call(paginate, repeats))
        frame_index = total // 2
        results["frame_http"] = summarize(time_call(
            lambda: client.get(
                f"/v2/races/{ordinary}/replay/frames/{frame_index}"),
            repeats))
        results["cached_prediction_http"] = summarize(time_call(
            lambda: client.get(
                f"/v2/races/{ordinary}/replay/predictions/"
                f"{checkpoint_frame.frame_index}"), repeats))
        results["probability_timeline_http"] = summarize(time_call(
            lambda: client.get(
                f"/v2/races/{ordinary}/replay/probability-timeline"),
            repeats))
    finally:
        app.dependency_overrides.pop(get_v2_replay_service, None)
    return results


def _regime_frame(states, race_id, timeline, tokens):
    rows = states[states["race_id"] == race_id]
    reps = {}
    for row in rows.itertuples(index=False):
        key = float(row.state_time_s)
        candidate = (int(row.lap_number), str(row.driver_id),
                     None if pd.isna(row.track_state)
                     else str(row.track_state))
        if key not in reps or candidate[:2] < reps[key][:2]:
            reps[key] = candidate
    for frame in timeline.frames:
        if reps[frame.anchor_state_time_s][2] in tokens:
            return frame.frame_index
    raise AssertionError(f"no {tokens} frame in {race_id}")


def _frame_near(service, race_id, target_t):
    for frame in service.get_timeline(race_id).frames:
        if abs(frame.anchor_state_time_s - target_t) < 1e-9:
            return frame.frame_index
    raise AssertionError(f"no frame near {target_t} in {race_id}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Phase-5 replay benchmark.")
    parser.add_argument("--repeats", type=int, default=25,
                        help="samples per operation (default 25)")
    parser.add_argument("--json", default=None,
                        help="optional path to write the results as JSON")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    results = run(args.repeats)
    for name, metrics in results.items():
        if not isinstance(metrics, dict) or "n" not in metrics:
            print(f"{name}: {metrics}")
            continue
        line = (f"{name}: n={metrics['n']} mean={metrics['mean_ms']:.2f} "
                f"p50={metrics['p50_ms']:.2f} "
                f"p95={'n/a' if metrics['p95_ms'] is None else format(metrics['p95_ms'], '.2f')} "
                f"p99={'n/a' if metrics['p99_ms'] is None else format(metrics['p99_ms'], '.2f')} "
                f"min={metrics['min_ms']:.2f} max={metrics['max_ms']:.2f} "
                f"(ms)")
        print(line)
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(results, handle, indent=2, sort_keys=True)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
