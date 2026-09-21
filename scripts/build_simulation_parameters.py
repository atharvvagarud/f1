"""Build the Phase-6 R3 empirical simulation-parameter artifact.

Offline, deterministic, chronological. Requires an explicit estimation
cutoff; never reads 2025. Writes only under ``data/v2/`` (repository-
untracked generated data, like the canonical Parquet it is derived from).

Usage:
    python scripts/build_simulation_parameters.py --through-season 2024
    python scripts/build_simulation_parameters.py --through-season 2022 \
        --out-dir /tmp/params2022

The artifact is ``manifest.json``: a versioned, hash-addressed parameter
set consumed read-only by ``v2.simulation.params.load_simulation_parameters``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v2.config import V2Paths  # noqa: E402
from v2.simulation.params import (  # noqa: E402
    PARAMETER_MANIFEST_FILENAME,
    parameter_storage_dir,
)
from v2.simulation.estimator import (  # noqa: E402
    SEASON_MAX,
    SEASON_MIN,
    estimate_simulation_parameters,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through-season", type=int, required=True,
        help=f"last estimation season, inclusive ({SEASON_MIN}-{SEASON_MAX}); "
             "2025 is never read")
    parser.add_argument(
        "--project-root", default=None,
        help="repository root (default: discover from cwd)")
    parser.add_argument(
        "--out-dir", default=None,
        help="output directory (default: data/v2/simulation/params/<...>)")
    parser.add_argument(
        "--created-at", default=None,
        help="optional ISO timestamp recorded in creation metadata only; "
             "never part of the scientific hash")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not (SEASON_MIN <= args.through_season <= SEASON_MAX):
        print(
            f"error: --through-season must be within "
            f"[{SEASON_MIN}, {SEASON_MAX}], got {args.through_season}",
            file=sys.stderr)
        return 2
    paths = V2Paths.resolve(args.project_root)
    creation_metadata = {
        "generator": "scripts/build_simulation_parameters.py",
        "estimator_version": None,  # filled below
    }
    if args.created_at:
        creation_metadata["created_at_utc"] = args.created_at
    parameter_set = estimate_simulation_parameters(
        paths, through_season=args.through_season,
        creation_metadata=creation_metadata)
    creation_metadata["estimator_version"] = parameter_set.estimator_version

    out_dir = (Path(args.out_dir) if args.out_dir
               else parameter_storage_dir(paths.root, args.through_season))
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / PARAMETER_MANIFEST_FILENAME
    manifest_path.write_text(parameter_set.to_json() + "\n", encoding="utf-8")

    diag = parameter_set.diagnostics
    print(json.dumps({
        "manifest": str(manifest_path),
        "parameter_set_id": parameter_set.parameter_set_id,
        "parameter_version": parameter_set.parameter_version,
        "scientific_hash": parameter_set.scientific_hash(),
        "through_season": parameter_set.through_season,
        "estimation_seasons": list(parameter_set.estimation_seasons),
        "eligible_lap_count": diag["eligible_lap_count"],
        "artifact_bytes": manifest_path.stat().st_size,
        "families": sorted(parameter_set.families),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
