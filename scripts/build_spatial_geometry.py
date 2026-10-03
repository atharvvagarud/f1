"""Build P12-3 circuit geometry from canonical spatial observations.

Canonical geometry entry point (separate from observation ingestion):

    python scripts/build_spatial_geometry.py --race 2021-r05-R
    python scripts/build_spatial_geometry.py --season 2023
    python scripts/build_spatial_geometry.py --list
    python scripts/build_spatial_geometry.py --force --race 2023-r01-R

Source authority is the P12-2 observation manifest: geometry is
generated only for COMPLETE/PARTIAL observation rows (UNAVAILABLE/
FAILED sources become SKIPPED geometry rows, never fabricated).
Default resumes verified geometries; `--force` rebuilds selection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raceintel.spatial import geometry as G
from raceintel.spatial.io import (
    artifact_path,
    geometry_dir,
    geometry_manifest_path,
    geometry_path,
    load_geometry_manifest,
    load_manifest,
    manifest_path,
    read_observations,
    save_geometry_manifest,
    write_geometry_atomic,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="P12-3 circuit geometry generation")
    parser.add_argument("--root", default=str(ROOT),
                        help="project root (default: repository root)")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--race", default=None)
    parser.add_argument("--force", action="store_true",
                        help="rebuild selected races even when verified")
    parser.add_argument("--list", action="store_true",
                        help="dry run: list eligible races, build nothing")
    return parser.parse_args(argv)


def _eligible_universe(root: Path):
    """(race_id, observation status, source hash|None) from P12-2."""
    manifest = load_manifest(manifest_path(root))
    universe = []
    for race_id in sorted(manifest["races"]):
        row = manifest["races"][race_id]
        status = row.get("status")
        if status in ("COMPLETE", "PARTIAL"):
            universe.append((race_id, status,
                             row["provenance"]["content_sha256"]))
        else:
            universe.append((race_id, status, None))
    return universe


def build_one(root: Path, race_id: str, source_hash: str) -> dict:
    """Derive + validate + persist one geometry (raises GeometryError)."""
    frame = read_observations(artifact_path(root, race_id))
    record = G.build_geometry(race_id, frame, data_root=root)
    record["source"]["observation_content_sha256"] = source_hash
    record["content_sha256"] = G.geometry_content_hash(record)
    G.validate_geometry(record)
    write_geometry_atomic(record, geometry_path(root, race_id))
    return record


def main(argv=None) -> int:
    args = _parse_args(argv)
    root = Path(args.root).resolve()
    universe = _eligible_universe(root)
    if args.season is not None:
        universe = [e for e in universe
                    if int(e[0][:4]) == args.season]
    if args.race is not None:
        universe = [e for e in universe if e[0] == args.race]
    if args.race is not None and not universe:
        print(f"race {args.race} not in the P12-2 manifest", file=sys.stderr)
        return 2
    if args.list:
        for race_id, status, _ in universe:
            print(f"{race_id} observations={status}")
        print(f"universe={len(universe)}")
        return 0

    manifest_file = geometry_manifest_path(root)
    manifest = load_geometry_manifest(manifest_file)
    counts = {"skipped": 0, "complete": 0, "failed": 0, "geom-skipped": 0}
    started = time.time()
    for race_id, obs_status, source_hash in universe:
        previous = manifest["races"].get(race_id)
        if obs_status not in ("COMPLETE", "PARTIAL"):
            manifest = G.set_geometry_row(
                manifest, race_id, status=G.GEOMETRY_STATUS_SKIPPED,
                reason=f"source observations {obs_status} "
                       f"(P12-2 manifest); geometry not generated")
            save_geometry_manifest(manifest, manifest_file)
            counts["geom-skipped"] += 1
            print(f"SKIPPED {race_id} (observations {obs_status})",
                  flush=True)
            continue
        if (not args.force and previous is not None
                and G.verify_geometry_artifact(
                    geometry_dir(root), race_id, previous, source_hash)):
            counts["skipped"] += 1
            print(f"SKIP {race_id} (verified geometry, resume)", flush=True)
            continue
        if args.force:
            print(f"REBUILD {race_id} (--force)", flush=True)
        try:
            t0 = time.time()
            record = build_one(root, race_id, source_hash)
            manifest = G.set_geometry_row(
                manifest, race_id, status=G.GEOMETRY_STATUS_COMPLETE,
                source_content_sha256=source_hash,
                geometry_sha256=record["content_sha256"],
                n_points=record["main_track"]["n_points"],
                pit_status=record["pit_status"])
            save_geometry_manifest(manifest, manifest_file)
            counts["complete"] += 1
            print(f"COMPLETE {race_id} pit={record['pit_status']} "
                  f"n={record['main_track']['n_points']} "
                  f"{time.time()-t0:.1f}s", flush=True)
        except Exception as exc:
            manifest = G.set_geometry_row(
                manifest, race_id, status=G.GEOMETRY_STATUS_FAILED,
                reason=f"{type(exc).__name__}: {exc}")
            save_geometry_manifest(manifest, manifest_file)
            counts["failed"] += 1
            print(f"FAILED {race_id} :: {type(exc).__name__}: {exc}",
                  flush=True)
    elapsed = time.time() - started
    identity = save_geometry_manifest(manifest, manifest_file)
    print(json.dumps({"selected": len(universe), "counts": counts,
                      "wall_s": round(elapsed, 1),
                      "manifest_sha256": identity,
                      "algorithm_version": G.GEOMETRY_ALGORITHM_VERSION}))
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
