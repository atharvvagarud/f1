"""Build the P12-2 historical spatial observation corpus.

Canonical developer entry point (one CLI; no competing surface):

    python scripts/build_spatial_observations.py --season 2023
    python scripts/build_spatial_observations.py --race 2021-r05-R
    python scripts/build_spatial_observations.py --list
    python scripts/build_spatial_observations.py --force --race 2023-r01-R

Default: cache-only source, resume verified COMPLETE artifacts. No
network is required when the local FastF1 cache is present; missing
sources are recorded UNAVAILABLE, never downloaded. ``--source-mode
network`` is explicitly opt-in and clearly separated.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raceintel.spatial import ingestion as ING
from raceintel.spatial import manifest as SM
from raceintel.spatial.io import load_manifest, manifest_path, save_manifest


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="P12-2 historical spatial observation ingestion")
    parser.add_argument("--root", default=str(ROOT),
                        help="project root (default: repository root)")
    parser.add_argument("--season", type=int, default=None,
                        help="ingest one season only (e.g. 2023)")
    parser.add_argument("--race", default=None,
                        help="ingest one race only (e.g. 2021-r05-R)")
    parser.add_argument("--source-mode", default=ING.SOURCE_MODE_CACHE_ONLY,
                        choices=list(ING.SOURCE_MODES))
    parser.add_argument("--force", action="store_true",
                        help="rebuild selected races even when verified "
                             "COMPLETE (default: resume/skip)")
    parser.add_argument("--list", action="store_true",
                        help="dry run: list the selected universe, "
                             "ingest nothing")
    parser.add_argument("--cache-dir", default=None,
                        help="FastF1 cache dir (default: "
                             "<root>/data/raw/fastf1_cache)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    root = Path(args.root).resolve()
    cache_dir = (Path(args.cache_dir) if args.cache_dir
                 else root / "data" / "raw" / "fastf1_cache")
    universe = ING.discover_universe(root)
    if args.season is not None:
        universe = [e for e in universe if e["season"] == args.season]
    if args.race is not None:
        universe = [e for e in universe if e["race_id"] == args.race]
    if args.season is not None and not universe:
        print(f"no Tier-A units for season {args.season}", file=sys.stderr)
        return 2
    if args.race is not None and not universe:
        print(f"race {args.race} not in the Tier-A universe",
              file=sys.stderr)
        return 2
    if args.list:
        for entry in universe:
            print(f"{entry['race_id']} season={entry['season']} "
                  f"round={entry['round_no']}")
        print(f"universe={len(universe)} "
              f"source-mode={args.source_mode}")
        return 0

    manifest_file = manifest_path(root)
    manifest = load_manifest(manifest_file)
    counts = {"skipped": 0, "complete": 0, "partial": 0,
              "unavailable": 0, "failed": 0, "reused-row-kept": 0}
    started = time.time()
    for entry in universe:
        race_id = entry["race_id"]
        previous = manifest["races"].get(race_id)
        if (not args.force and previous is not None
                and previous.get("status") == SM.STATUS_COMPLETE
                and previous.get("provenance") is not None
                and ING.verify_complete_artifact(
                    root, race_id, previous["provenance"])):
            counts["skipped"] += 1
            print(f"SKIP {race_id} (verified COMPLETE, resume)")
            continue
        if args.force:
            print(f"REBUILD {race_id} (--force)")
        result = ING.ingest_race(entry["season"], entry["round_no"],
                                 race_id, root=root, cache_dir=cache_dir,
                                 source_mode=args.source_mode)
        status = result["status"]
        manifest, disposition = ING.apply_result(manifest, result,
                                                previous, root)
        save_manifest(manifest, manifest_file)
        if status == SM.STATUS_COMPLETE:
            counts["complete"] += 1
        elif status == SM.STATUS_PARTIAL:
            counts["partial"] += 1
        elif status == SM.STATUS_UNAVAILABLE:
            counts["unavailable"] += 1
            if disposition == "kept-previous":
                counts["reused-row-kept"] += 1
        else:
            counts["failed"] += 1
            if disposition == "kept-previous":
                counts["reused-row-kept"] += 1
        detail = ""
        if status in (SM.STATUS_FAILED, SM.STATUS_UNAVAILABLE):
            detail = f" :: {result['reason']}"
        elif status == SM.STATUS_PARTIAL:
            detail = f" :: {result['reason']}"
        print(f"{status} {race_id}{detail}", flush=True)
    elapsed = time.time() - started
    identity = save_manifest(manifest, manifest_file)
    print(json.dumps({"selected": len(universe), "counts": counts,
                      "wall_s": round(elapsed, 1),
                      "manifest_sha256": identity,
                      "ingestion_version": ING.INGESTION_VERSION,
                      "source_mode": args.source_mode}))
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
