"""V3.6F deterministic Strategy 2.0 cache generator.

Builds cache artifacts with the validated V3.6C engine (via the V3.6F
runtime service live path; no strategy math is duplicated here). Each
artifact covers the FULL frozen 9-action set for one
(state, target, seed) triple at the frozen 5000 production configuration.

Usage:
    .venv/bin/python scripts/v3_6f_build_strategy_cache.py --fixture
    .venv/bin/python scripts/v3_6f_build_strategy_cache.py \\
        --anchors-json path/to/anchors.json --cache-dir <dir>

Anchors JSON: list of {race_id, anchor_driver_id, anchor_lap_number,
anchor_state_time_s, target_driver_id}.

Properties: deterministic ordering, resume-safe (valid existing artifacts
are skipped), atomic writes, provenance validation before every write,
explicit unsupported records (unsupported states produce artifacts with
supported=false, never fabricated numbers), progress reporting and a
failure summary (nonzero exit on failures; unsupported is not failure).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.v2_service import load_v2_service
from api.v2_strategy_v3_service import (
    DEFAULT_MASTER_SEED,
    PRODUCTION_SIMULATION_COUNT,
    V3CacheInvalidError,
    V3CacheMissError,
    artifact_hash,
    build_cache_artifact,
    build_cache_key,
    build_manifest,
    build_v3_strategy_service,
    read_cache_artifact,
    validate_cached_artifact,
    write_cache_artifact,
)

ROOT = Path(__file__).resolve().parents[1]

#: Deterministic representative fixture: one supported real state plus one
#: scientifically unsupported state (proves explicit unsupported records).
FIXTURE_ANCHORS = [
    {"race_id": "2022-r01-R", "anchor_driver_id": "perez",
     "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
     "target_driver_id": "perez"},
    {"race_id": "2018-r11-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 44, "anchor_state_time_s": 4004.408,
     "target_driver_id": "alonso"},
]

#: Engine-shaped fields stored in cache artifacts (presentation-only
#: runtime/execution-source fields never enter the cache).
SCIENTIFIC_FIELDS = (
    "engine_version", "execution_contract_version",
    "outcome_schema_version", "strategy_identity", "state_identity",
    "parameter_identity", "config_identity", "master_seed",
    "simulation_count", "target_driver_id", "supported",
    "unsupported_reason", "reference_kind", "alternatives", "leaders",
    "provenance",
)


def _scientific_from_payload(payload: dict) -> dict:
    return {k: payload[k] for k in SCIENTIFIC_FIELDS}


def _load_anchors(path: Path) -> list:
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ValueError("anchors JSON must be a list")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic Strategy 2.0 cache artifacts.")
    parser.add_argument("--fixture", action="store_true",
                        help="use the built-in representative fixture")
    parser.add_argument("--anchors-json", default=None,
                        help="JSON list of anchor dicts")
    parser.add_argument("--cache-dir", default=None,
                        help="cache directory (default: production path)")
    parser.add_argument("--seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--manifest-out", default=None,
                        help="manifest JSON path (default: "
                             "results/v3/v3_6f/cache_manifest.json)")
    args = parser.parse_args()

    if args.fixture:
        anchors = list(FIXTURE_ANCHORS)
    elif args.anchors_json:
        anchors = _load_anchors(Path(args.anchors_json))
    else:
        print("specify --fixture or --anchors-json", file=sys.stderr)
        return 2
    anchors = sorted(
        anchors,
        key=lambda a: (a["race_id"], a["anchor_lap_number"],
                       str(a["anchor_state_time_s"]),
                       a["target_driver_id"]))

    v2 = load_v2_service()
    service_kwargs: dict = {}
    if args.cache_dir:
        service_kwargs["cache_dir"] = Path(args.cache_dir)
    service = build_v3_strategy_service(v2, **service_kwargs)
    assert (service.simulation_count == PRODUCTION_SIMULATION_COUNT), (
        "generator must use the frozen 5000 production configuration")
    cache_dir = service.cache_dir

    manifest_out = (Path(args.manifest_out) if args.manifest_out
                    else ROOT / "results" / "v3" / "v3_6f"
                    / "cache_manifest.json")

    entries, failures, skipped = [], [], 0
    t0 = time.perf_counter()
    for i, anchor in enumerate(anchors, 1):
        label = (f"{anchor['race_id']}/{anchor['anchor_driver_id']}"
                 f"/lap{anchor['anchor_lap_number']}"
                 f"->{anchor['target_driver_id']}")
        print(f"[{i}/{len(anchors)}] {label} ...", flush=True)
        try:
            payload = service.run_comparison(
                race_id=anchor["race_id"],
                anchor_driver_id=anchor["anchor_driver_id"],
                anchor_lap_number=anchor["anchor_lap_number"],
                anchor_state_time_s=anchor["anchor_state_time_s"],
                target_driver_id=anchor["target_driver_id"],
                alternatives=None, master_seed=args.seed, mode="live")
        except Exception as exc:  # noqa: BLE001 - record, never guess
            failures.append({"anchor": anchor,
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        scientific = _scientific_from_payload(payload)
        key = build_cache_key(
            state_identity=scientific["state_identity"],
            parameter_identity=scientific["parameter_identity"],
            config_identity=scientific["config_identity"],
            simulation_count=scientific["simulation_count"],
            master_seed=scientific["master_seed"],
            target_driver_id=scientific["target_driver_id"])
        assert key == payload["cache_key"], "cache key drift (refusing)"
        artifact = build_cache_artifact(
            cache_key=key, result_dict=scientific,
            request_meta={
                "race_id": anchor["race_id"],
                "anchor_driver_id": anchor["anchor_driver_id"],
                "anchor_lap_number": anchor["anchor_lap_number"],
                "anchor_state_time_s": anchor["anchor_state_time_s"],
                "target_driver_id": anchor["target_driver_id"],
                "master_seed": args.seed,
            })
        # Resume-safe: skip valid existing artifacts.
        try:
            existing = read_cache_artifact(cache_dir, key)
            validate_cached_artifact(
                existing, cache_key=key,
                state_identity=scientific["state_identity"],
                parameter_identity=scientific["parameter_identity"],
                config_identity=scientific["config_identity"],
                simulation_count=scientific["simulation_count"],
                master_seed=scientific["master_seed"],
                target_driver_id=scientific["target_driver_id"])
            skipped += 1
            print(f"  skip (valid existing {key[:12]}…)", flush=True)
        except (V3CacheMissError, V3CacheInvalidError):
            path = write_cache_artifact(cache_dir, artifact)
            print(f"  wrote {path.name} "
                  f"supported={scientific['supported']}", flush=True)
        entries.append({
            "race_id": anchor["race_id"],
            "anchor_driver_id": anchor["anchor_driver_id"],
            "anchor_lap_number": anchor["anchor_lap_number"],
            "anchor_state_time_s": anchor["anchor_state_time_s"],
            "target_driver_id": anchor["target_driver_id"],
            "master_seed": scientific["master_seed"],
            "simulation_count": scientific["simulation_count"],
            "supported": scientific["supported"],
            "unsupported_reason": scientific["unsupported_reason"],
            "alternative_count": len(scientific["alternatives"]),
            "comparison_identities": sorted(
                a.get("comparison_identity")
                for a in scientific["alternatives"]
                if a.get("comparison_identity")),
            "cache_key": key,
            "artifact_hash": artifact_hash(artifact),
            "status": "ok",
        })

    manifest = build_manifest(entries, status="fixture"
                              if args.fixture else "build")
    manifest["generation"] = {
        "seed": args.seed,
        "anchor_count": len(anchors),
        "artifact_count": len(entries),
        "skipped_existing": skipped,
        "failures": failures,
        "wall_s": time.perf_counter() - t0,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_out.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, sort_keys=True, indent=2))
    tmp.replace(manifest_out)
    print(f"anchors={len(anchors)} artifacts={len(entries)} "
          f"skipped={skipped} failures={len(failures)} "
          f"wall_s={manifest['generation']['wall_s']:.1f}")
    for failure in failures:
        print(f"FAILURE {failure['anchor']}: {failure['error']}",
              file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
