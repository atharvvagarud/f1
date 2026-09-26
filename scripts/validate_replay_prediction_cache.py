"""E2 read-only corpus validator for the production replay cache.

Loads artifacts, recomputes model-free checkpoint selection, validates
identities (series/model/cache-key), probability/null semantics and
temporal ordering, and produces:
  results/v2_replay/phase8_e2_cache_manifest_v1.json

READ ONLY: never generates predictions, repairs cache, touches 2025
targets, or rewrites scientific artifacts.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from api.v2_service import SERVED_SEASONS
from v2 import replay as RP
from v2.replay_predictions import (
    ARTIFACT_FORMAT,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    cache_key,
    canonical_data_identity,
    load_validated_artifact,
    select_checkpoints,
    series_identity,
)

FROZEN_MODEL_SHA = "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
FROZEN_SPEC_FP = "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d"
FROZEN_PHASE2 = "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
FROZEN_MATRIX_SHA = "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3"


def sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def served_race_ids() -> list:
    found = []
    for season in SERVED_SEASONS:
        pattern = os.path.join(
            REPO_ROOT, "data", "v2", "processed", "results",
            f"season={season}", "results__*.parquet")
        for path in sorted(glob.glob(pattern)):
            base = os.path.basename(path)
            found.append(base[len("results__"):-len(".parquet")])
    return found


def validate_corpus(checkpoints_dir: str) -> dict:
    started = time.time()
    races = served_race_ids()
    assert len(races) == 149, f"served race count {len(races)} != 149"
    assert [r for r in races if r.startswith("2025-")] == []

    artifact_files = sorted(glob.glob(
        os.path.join(checkpoints_dir, "*.json")))
    names = sorted(os.path.basename(p)[:-len(".json")]
                   for p in artifact_files)
    assert names == sorted(races), "artifact set != served race set"

    base = os.path.join(REPO_ROOT, "data", "v2", "processed")
    model_identity = None
    total_ckpts = total_obs = total_null = 0
    unavailable_reasons: dict = {}
    per_race: list = []
    for race_id in races:
        season = int(race_id.split("-")[0])
        states = pd.read_parquet(os.path.join(
            base, "driver_lap_state_d9", f"season={season}",
            f"driver_lap_state_d9__d9-{season}.parquet"))
        states = states[states["race_id"] == race_id].copy()
        timeline = RP.build_replay_timeline(states)
        series = select_checkpoints(timeline, states)
        path = os.path.join(checkpoints_dir, f"{race_id}.json")
        data_identity = canonical_data_identity(states, race_id)
        # Recompute expected cache identity from frozen inputs.
        with open(path) as handle:
            artifact = json.load(handle)
        assert artifact["artifact_format"] == ARTIFACT_FORMAT
        assert artifact["complete"] is True
        assert artifact["series"] == series.to_dict()
        assert artifact["cache_identity"]["canonical_data_identity"] == \
            data_identity
        assert artifact["cache_identity"]["series_identity"] == \
            series_identity(series)
        assert artifact["cache_key"] == cache_key(
            artifact["cache_identity"])
        load_validated_artifact(
            path, expected_inputs=artifact["cache_identity"], series=series)
        model = artifact["model"]
        if model_identity is None:
            model_identity = model
            assert model["artifact_sha256"] == FROZEN_MODEL_SHA
            assert model["specification_fingerprint"] == FROZEN_SPEC_FP
            assert model["feature_set"] == "ALL_84"
            assert model["feature_set_version"] == "v8"
            assert model["calibration_method"] == "RAW"
            assert model["probability_semantics"] == "INDEPENDENT_BINARY"
            assert artifact["cache_identity"]["phase2_content_hash"] == \
                FROZEN_PHASE2
        else:
            assert model == model_identity, f"mixed model identity {race_id}"
        assert artifact["prediction_contract_version"] == \
            REPLAY_PREDICTION_CONTRACT_VERSION
        assert artifact["replay_contract_version"] == \
            RP.REPLAY_CONTRACT_VERSION
        # Checkpoint/temporal/probability validation.
        assert len(artifact["checkpoints"]) == series.checkpoint_count
        race_obs = race_null = 0
        prev_t = None
        for entry, expected in zip(artifact["checkpoints"],
                                   series.checkpoints):
            assert entry["checkpoint"] == expected.to_dict()
            pred = entry["prediction"]
            assert pred["probability_semantics"] == "INDEPENDENT_BINARY"
            assert pred["roster_size"] == len(pred["predictions"])
            ids = [d["driver_id"] for d in pred["predictions"]]
            assert ids == sorted(ids)
            t = pred["state_time_s"]
            if prev_t is not None:
                assert t > prev_t
            prev_t = t
            for driver in pred["predictions"]:
                prob = driver["winner_probability"]
                if prob is None:
                    race_null += 1
                    reason = driver["unavailable_reason"]
                    assert isinstance(reason, str) and reason
                    unavailable_reasons[reason] = \
                        unavailable_reasons.get(reason, 0) + 1
                else:
                    assert not isinstance(prob, bool)
                    assert math.isfinite(prob) and 0.0 <= prob <= 1.0
                    race_obs += 1
        total_ckpts += series.checkpoint_count
        total_obs += race_obs
        total_null += race_null
        per_race.append({
            "race_id": race_id,
            "checkpoint_count": series.checkpoint_count,
            "observable_prediction_count": race_obs,
            "null_prediction_count": race_null,
            "cache_key": artifact["cache_key"],
            "artifact_sha256": sha_file(path),
            "validation_status": "valid",
        })
    assert total_ckpts == 9644, f"checkpoint total {total_ckpts} != 9644"
    # Aggregate corpus identity: sha256 over sorted race_id + artifact sha.
    digest = hashlib.sha256()
    for entry in sorted(per_race, key=lambda r: r["race_id"]):
        digest.update(entry["race_id"].encode())
        digest.update(entry["artifact_sha256"].encode())
    manifest = {
        "manifest_version": "phase8-e2-cache-manifest-v1",
        "generation_mode": "matrix",
        "served_seasons": list(SERVED_SEASONS),
        "race_count": len(per_race),
        "checkpoint_count": total_ckpts,
        "observable_prediction_count": total_obs,
        "null_prediction_count": total_null,
        "unavailable_reasons": unavailable_reasons,
        "model_identity": model_identity,
        "matrix_sha256": FROZEN_MATRIX_SHA,
        "phase2_content_hash": FROZEN_PHASE2,
        "aggregate_corpus_sha256": digest.hexdigest(),
        "validation_seconds": round(time.time() - started, 1),
        "races": sorted(per_race, key=lambda r: r["race_id"]),
    }
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only E2 replay cache corpus validator.")
    parser.add_argument("--checkpoints-dir", default=os.path.join(
        REPO_ROOT, "results", "v2_replay", "checkpoints"))
    parser.add_argument("--out", default=os.path.join(
        REPO_ROOT, "results", "v2_replay",
        "phase8_e2_cache_manifest_v1.json"))
    args = parser.parse_args(argv)
    manifest = validate_corpus(args.checkpoints_dir)
    with open(args.out, "w") as handle:
        json.dump(manifest, handle, sort_keys=True, separators=(",", ":"),
                  allow_nan=False)
    print(f"valid: races={manifest['race_count']} "
          f"checkpoints={manifest['checkpoint_count']} "
          f"observable={manifest['observable_prediction_count']} "
          f"null={manifest['null_prediction_count']} "
          f"aggregate={manifest['aggregate_corpus_sha256'][:16]}... "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
